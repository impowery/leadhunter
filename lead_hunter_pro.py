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

from datetime import datetime, timezone

import requests
from openai import OpenAI
from telethon import TelegramClient

GROQ_KEY = os.getenv("GROQ_API_KEY")
OR_KEY = os.getenv("OPENROUTER_API_KEY")
OR_KEY2 = os.getenv("OPENROUTER_API_KEY2")
TH_KEY = os.getenv("TOKENHARBOR_API_KEY")

groq_client = OpenAI(api_key=GROQ_KEY, base_url="https://api.groq.com/openai/v1") if GROQ_KEY else None
or_client = OpenAI(api_key=OR_KEY, base_url="https://openrouter.ai/api/v1") if OR_KEY else None
or_client2 = OpenAI(api_key=OR_KEY2, base_url="https://openrouter.ai/api/v1") if OR_KEY2 else None
th_client = OpenAI(api_key=TH_KEY, base_url="https://tokenharbor.ai/v1") if TH_KEY else None

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
    "n8n", "n8n workflow", "zapier", "make.com", "low-code", "no-code",
    "workflow automation", "process automation", "ai automation",
    "llm workflow", "llm integration", "prompt engineering", "ai agent",
    "generative ai", "chatbot", "telegram bot", "discord bot", "rag",
    "langchain", "webhook", "api integration", "rest api integration",
    "software integration", "system integration", "implementation",
    "scraping", "web scraping", "data extraction", "data pipeline", "etl",
    "selenium", "browser automation", "lead generation automation",
    "content automation", "customer support automation", "ai operations",
    "ai ops", "agent evaluation", "llm evaluation", "vector database",
    "freelance", "contract", "consultant", "remote", "saas", "mvp",
    "telegram automation", "payment integration", "e-commerce automation",
    "web3 automation", "defi automation", "crypto payment integration",
    "trading operations", "trading automation", "trading bot", "algorithmic trading",
    "portfolio reporting", "portfolio automation", "risk monitoring", "risk dashboard",
    "market data", "pnl reporting", "p&l reporting", "fee reconciliation",
    "trade journal", "broker integration", "exchange integration", "financial dashboard",
    "investment research automation", "drawdown alerts", "prop trading", "forex automation",
    "futures trading", "equity trading", "commodities trading",
    "treasury", "treasury operations", "settlement", "reconciliation", "fintech",
    "payments", "payment operations", "capital markets", "brokerage", "trading support",
    "market operations", "investment operations", "portfolio operations", "compliance",
    "risk analyst", "risk management", "financial operations", "accounting automation",
    "financial analyst", "investment analyst", "portfolio analyst", "quantitative analyst",
    "trading operations associate", "trade support", "middle office", "back office",
    "kyb", "kyc", "financial", "financial analyst", "trust operations",
    "operations analyst", "compliance officer", "payments analyst", "tax analyst",
    "fixed income", "equity research", "credit analyst", "finance associate",
    "trading assistant", "wealth", "client service", "payments operations",
]

EXCLUDE = [
    "senior", "sr.", "team lead", "tech lead", "engineering lead",
    "lead developer", "lead engineer", "lead architect", "lead designer",
    "lead recruiter", "principal", "staff", "head of",
    "director", "vp", "vice president", "manager",
    "account executive", "sales", "business development", "marketing", "growth marketing",
    "product marketing", "customer success", "customer support", "support agent",
    "recruiter", "recruiting", "legal", "counsel", "product designer", "ux designer",
    "frontend", "front-end", "mobile developer", "ios developer", "android developer",
    "video maker", "video editor", "3d artist", "social media", "community manager",
    "security engineer", "security analyst", "solidity engineer", "rust engineer",
    "quant developer", "data scientist", "machine learning scientist", "ml researcher",
    "research intern", "english tutor", "online tutor", "teacher",
    "onsite", "on-site", "office-based", "in-office", "hybrid",
    "accountant", "accounting", "bookkeeper", "bookkeeping", "controller", "chief accountant",
    "accounts payable", "accounts receivable", "payroll", "audit", "auditor", "auditing",
    "shopify", "node.js", "nodejs", "node js", "typescript", "react", "vue", "django", "fastapi",
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

TELEGRAM_JOB_HINTS = (
    "vacancy", "job", "hiring", "looking for", "we are looking", "position",
    "developer", "engineer", "automation", "workflow", "n8n", "zapier", "make.com",
    "llm", "chatbot", "ai agent", "integration", "scraping", "freelance", "contract",
    "remote", "apply", "salary", "compensation", "вакансия", "требуется", "ищем",
    "нужен", "работа", "удаленно", "удалённо", "проект", "оплата", "отклик",
)
TELEGRAM_NOISE = (
    "burger", "pizza", "restaurant", "menu", "delivery", "доставка", "бургер",
    "пицца", "меню", "скидка", "реклама", "casino", "ставки",
)


MAX_LEAD_AGE_DAYS = 30  # ignore leads older than this (e.g. "10mo ago")


def parse_lead_date(val):
    """Parse a date from various formats into epoch seconds (float) or None.
    Accepts ISO-8601, RFC 822 (RSS pubDate), and epoch ints/strings."""
    if val is None:
        return None
    s = str(val).strip()
    if not s:
        return None
    if s.lstrip("-").isdigit():
        n = int(s)
        # seconds vs ms vs us heuristic
        if n > 10**15:
            n = n // 10**6
        elif n > 10**12:
            n = n // 10**3
        return float(n)
    s2 = re.sub(r"Z$", "+00:00", s)
    for fmt in (
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S.%f%z",
        "%Y-%m-%d %H:%M:%S%z",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d",
    ):
        for base in (s2, s2 + "+00:00"):
            try:
                dt = datetime.strptime(base, fmt)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt.timestamp()
            except (ValueError, TypeError):
                continue
    try:
        from email.utils import parsedate_to_datetime
        dt = parsedate_to_datetime(s)
        if dt is not None:
            return dt.replace(tzinfo=dt.tzinfo or timezone.utc).timestamp()
    except Exception:
        pass
    return None


def age_ago_epoch(text):
    """Detect textual age markers like '1y ago', '10mo ago', '3 months ago',
    '2 weeks ago', '5 days ago' in a title/description -> approx epoch, else None."""
    if not text:
        return None
    now = time.time()
    m = re.search(r"(\d+)\+?\s*(y|yr|yrs|year|years)\s*ago", text, re.I)
    if m:
        return now - int(m.group(1)) * 365 * 86400
    m = re.search(r"(\d+)\+?\s*(mo|mth|mths|month|months)\s*ago", text, re.I)
    if m:
        return now - int(m.group(1)) * 30 * 86400
    m = re.search(r"(\d+)\+?\s*(w|wk|wks|week|weeks)\s*ago", text, re.I)
    if m:
        return now - int(m.group(1)) * 7 * 86400
    m = re.search(r"(\d+)\+?\s*(d|day|days)\s*ago", text, re.I)
    if m:
        return now - int(m.group(1)) * 86400
    return None


CLOSED_PATTERNS = (
    r"this job is closed",
    r"this job is no longer accepting applications",
    r"job is no longer accepting applications",
    r"no longer accepting applications",
    r"position has been filled",
    r"job closed",
    r"not accepting applications",
)


def lead_fresh(lead, max_days=MAX_LEAD_AGE_DAYS):
    """True if the lead is younger than max_days. Checks posted_at, then
    falls back to textual age markers ('3y ago') inside title/description.
    Explicitly-closed job postings are never fresh."""
    text = (lead.get("title") or "") + " " + (lead.get("description") or "")
    for pat in CLOSED_PATTERNS:
        if re.search(pat, text, re.I):
            return False
    age = lead.get("posted_at")
    if age is None:
        age = age_ago_epoch(text)
    if age is None:
        return True
    try:
        return (time.time() - float(age)) <= max_days * 86400
    except Exception:
        return True


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
    # migration: posted_at (epoch) for age-filtered digests/queues
    try:
        c.execute("ALTER TABLE leads ADD COLUMN posted_at REAL")
        conn.commit()
    except Exception:
        pass  # column already exists
    # kits: application letters generated for a lead
    try:
        c.execute(
            "CREATE TABLE IF NOT EXISTS kits (url TEXT PRIMARY KEY, letter TEXT, "
            "answers TEXT, created_at TEXT DEFAULT (datetime('now')))"
        )
        conn.commit()
    except Exception:
        pass
    # migration: evidence-based scoring columns
    for _col in ("fit REAL", "gates TEXT", "evidence TEXT"):
        try:
            c.execute("ALTER TABLE leads ADD COLUMN " + _col)
            conn.commit()
        except Exception:
            pass
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


SPECIFIC_KW = {
    "n8n", "n8n workflow", "zapier", "make.com", "low-code", "no-code",
    "workflow automation", "process automation", "ai automation", "llm workflow",
    "llm integration", "prompt engineering", "ai agent", "chatbot", "telegram bot",
    "rag", "langchain", "webhook", "api integration", "system integration",
    "implementation", "web scraping", "data extraction", "browser automation",
    "customer support automation", "ai operations", "ai ops", "agent evaluation",
    "llm evaluation", "telegram automation", "payment integration",
    "e-commerce automation", "web3 automation", "defi automation",
    "crypto payment integration",
    "trading operations", "trading automation", "trading bot", "algorithmic trading",
    "portfolio reporting", "portfolio automation", "risk monitoring", "risk dashboard",
    "market data", "pnl reporting", "p&l reporting", "fee reconciliation",
    "trade journal", "broker integration", "exchange integration", "financial dashboard",
    "investment research automation", "drawdown alerts", "prop trading", "forex automation",
    "futures trading", "equity trading", "commodities trading",
    "treasury", "treasury operations", "settlement", "reconciliation", "fintech",
    "payments", "payment operations", "capital markets", "brokerage", "trading support",
    "market operations", "investment operations", "portfolio operations", "compliance",
    "risk analyst", "risk management", "financial operations", "accounting automation",
    "financial analyst", "investment analyst", "portfolio analyst", "quantitative analyst",
    "trading operations associate", "trade support", "middle office", "back office",
    "kyb", "kyc", "financial", "financial analyst", "trust operations",
    "operations analyst", "compliance officer", "payments analyst", "tax analyst",
    "fixed income", "equity research", "credit analyst", "finance associate",
    "trading assistant", "wealth", "client service", "payments operations",
}
GENERAL_KW = {
    "freelance", "contract", "consultant", "remote", "saas", "mvp",
    "scraping", "data pipeline", "etl", "selenium", "rest api integration",
    "software integration", "generative ai", "vector database",
    "lead generation automation", "content automation",
    "financial operations", "trading infrastructure", "portfolio analytics",
    "investment", "trading", "finance", "crypto", "web3", "blockchain",
    "fintech", "risk", "operations",
}

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


# USD per 1M tokens (input, output). Tokenharbor list prices; free tiers are 0.
LLM_PRICES = {
    "claude-haiku-5.5": (0.10, 0.50),
    "claude-sonnet-4.6": (3.00, 15.00),
    "deepseek-v4.1-flash:free": (0.0, 0.0),
    "openai/gpt-oss-120b": (0.0, 0.0),
    "deepseek/deepseek-chat": (0.27, 1.10),
    "meta-llama/llama-3.3-70b-instruct": (0.12, 0.30),
    "qwen/qwen3.7-flash": (0.05, 0.10),
}
LLM_USAGE_LOG = os.path.join(DATA_DIR, "llm_usage.jsonl")
# Cheap-but-reliable model that drives letters and kits.
LLM_QUALITY_MODEL = os.getenv("LLM_QUALITY_MODEL", "claude-haiku-5.5")
# Stronger model, used only when the cheap tier returns unusable JSON.
LLM_ESCALATE_MODEL = os.getenv("LLM_ESCALATE_MODEL", "claude-sonnet-4.6")


def _llm_chain(tier="bulk"):
    """Cost-ordered (client, model) chain for one workload tier.

    bulk     - scoring runs over thousands of leads: free providers first, paid
               models only when the free ones keep failing.
    quality  - letters, kits, router prompts: cheap reliable model first, since
               volume is tiny and a failed JSON wastes the whole call.
    escalate - retry after the cheap tier returned unusable JSON.
    qwen goes last in every tier: it is frequently rate-limited upstream
    (429 -> empty content).
    """
    free, paid, ors = [], [], []
    if th_client:
        free.append((th_client, "deepseek-v4.1-flash:free"))
        paid.append((th_client, LLM_QUALITY_MODEL))
        if LLM_ESCALATE_MODEL:
            paid.append((th_client, LLM_ESCALATE_MODEL))
    if groq_client:
        free.append((groq_client, "openai/gpt-oss-120b"))
    if or_client:
        ors += [
            (or_client, "deepseek/deepseek-chat"),
            (or_client, "meta-llama/llama-3.3-70b-instruct"),
            (or_client, "qwen/qwen3.7-flash"),
        ]
    if or_client2:
        ors += [
            (or_client2, "deepseek/deepseek-chat"),
            (or_client2, "qwen/qwen3.7-flash"),
        ]

    if tier == "quality":
        chain = paid[:1] + free + paid[1:] + ors
    elif tier == "escalate":
        chain = paid[1:] + paid[:1] + free + ors
    elif os.getenv("LLM_BULK_FREE_FIRST", "1") != "0":
        chain = free + paid + ors
    else:
        # Escape hatch: paid models first when the free tiers are rate-limited.
        chain = paid + free + ors

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


def _llm_log_usage(tier, model, resp):
    """Append one JSONL line per successful call so spend stays measurable."""
    try:
        usage = getattr(resp, "usage", None)
        tok_in = int(getattr(usage, "prompt_tokens", 0) or 0)
        tok_out = int(getattr(usage, "completion_tokens", 0) or 0)
        price_in, price_out = LLM_PRICES.get(model, (0.0, 0.0))
        record = {
            "ts": int(time.time()),
            "tier": tier,
            "model": model,
            "in": tok_in,
            "out": tok_out,
            "usd": round((tok_in * price_in + tok_out * price_out) / 1_000_000, 6),
        }
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(LLM_USAGE_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")
    except Exception as e:
        print(f"  [WARN] usage log failed: {e}", flush=True)


def llm_usage_report(days=7):
    """Print calls and spend per tier/model for the last N days."""
    cutoff = time.time() - days * 86400
    if not os.path.exists(LLM_USAGE_LOG):
        print("No LLM usage recorded yet.")
        return
    rows = {}
    with open(LLM_USAGE_LOG, encoding="utf-8") as f:
        for line in f:
            try:
                r = json.loads(line)
            except Exception:
                continue
            if r.get("ts", 0) < cutoff:
                continue
            agg = rows.setdefault((r.get("tier", "?"), r.get("model", "?")), {"calls": 0, "in": 0, "out": 0, "usd": 0.0})
            agg["calls"] += 1
            agg["in"] += int(r.get("in", 0))
            agg["out"] += int(r.get("out", 0))
            agg["usd"] += float(r.get("usd", 0.0))
    total_calls = sum(v["calls"] for v in rows.values())
    total_usd = sum(v["usd"] for v in rows.values())
    print(f"LLM usage, last {days} days: {total_calls} calls, ${total_usd:.4f}")
    for (tier, model), v in sorted(rows.items(), key=lambda kv: -kv[1]["usd"]):
        print(
            f"  {tier:8s} {model:34s} {v['calls']:5d} calls "
            f"{v['in']:>8d} in {v['out']:>7d} out ${v['usd']:.4f}"
        )


_LLM_ALERT_STATE = os.path.join(DATA_DIR, "llm_alert.json")


def _llm_alert(reason):
    """One Telegram alert per 6 hours when every LLM provider fails."""
    try:
        now = time.time()
        last = 0
        if os.path.exists(_LLM_ALERT_STATE):
            try:
                last = float(json.load(open(_LLM_ALERT_STATE)).get("ts", 0))
            except Exception:
                last = 0
        if now - last < 6 * 3600:
            return
        send_tg_message(
            "🚨 <b>LLM scoring is down</b>\n"
            + str(reason)[:300]
            + "\n\nLeads are saved but NOT scored. Check API keys / credits."
        )
        json.dump({"ts": now}, open(_LLM_ALERT_STATE, "w"))
    except Exception as e:
        print(f"  [WARN] llm alert failed: {e}", flush=True)


def llm_complete(system, user, max_tokens=200, temperature=0.1, timeout=20, json_mode=False, tier="bulk"):
    """Try each (client, model) of the tier's chain with one retry each."""
    last_err = ""
    for client, model in _llm_chain(tier):
        for attempt in range(2):
            try:
                kwargs = {}
                budget = max_tokens
                if model.startswith("openai/gpt-oss"):
                    # reasoning models spend the token budget on hidden reasoning,
                    # so force low effort and keep a floor big enough for JSON output
                    kwargs["extra_body"] = {"reasoning_effort": "low"}
                    budget = max(max_tokens, 400)
                elif "deepseek-v4.1" in model:
                    # thinking model: keep a floor so JSON output is not cut off
                    budget = max(max_tokens, 900)
                if json_mode:
                    kwargs["response_format"] = {"type": "json_object"}
                try:
                    resp = client.chat.completions.create(
                        model=model,
                        messages=[
                            {"role": "system", "content": system},
                            {"role": "user", "content": user},
                        ],
                        temperature=temperature,
                        max_tokens=budget,
                        timeout=timeout,
                        **kwargs,
                    )
                except Exception:
                    if json_mode and "response_format" in kwargs:
                        kwargs.pop("response_format", None)
                        resp = client.chat.completions.create(
                            model=model,
                            messages=[
                                {"role": "system", "content": system},
                                {"role": "user", "content": user},
                            ],
                            temperature=temperature,
                            max_tokens=budget,
                            timeout=timeout,
                            **kwargs,
                        )
                    else:
                        raise
                raw = (resp.choices[0].message.content or "").strip()
                if raw:
                    _llm_log_usage(tier, model, resp)
                    return raw
                print(f"  [WARN] LLM empty response ({model})", flush=True)
                last_err = "empty response: " + model
                if model.startswith("openai/gpt-oss") and budget < 800:
                    resp = client.chat.completions.create(
                        model=model,
                        messages=[
                            {"role": "system", "content": system},
                            {"role": "user", "content": user},
                        ],
                        temperature=temperature,
                        max_tokens=800,
                        timeout=timeout,
                        extra_body={"reasoning_effort": "low"},
                    )
                    raw = (resp.choices[0].message.content or "").strip()
                    if raw:
                        _llm_log_usage(tier, model, resp)
                        return raw
            except Exception as e:
                print(f"  [WARN] LLM call failed ({model}): {e}", flush=True)
                last_err = f"{model}: {e}"
            time.sleep(1)
    _llm_alert(last_err or "no LLM providers configured")
    return None


def llm_score(title, description, allow_senior=False, prompt=None):
    text = f"Title: {title}\nDescription: {description}"

    kw = keyword_score(text, allow_senior=allow_senior)
    if prompt is None and kw["score"] < 2:
        return kw

    senior_rule = (
        "IMPORTANT: Keep reason short. If the title says Senior, Lead, Principal, Director, VP, or Head Of, set gates.eligibility to fail.\n"
    )
    if prompt is None:
        model_prompt = (
            "You are an expert AI scorer for this profile: an AI automation builder "
            "who assembles practical LLM workflows and integrations. Strong areas are "
            "n8n/Make/Zapier-style automation, LLM and chatbot integrations, web scraping, "
            "data extraction, webhooks, API integrations, Telegram bots, AI operations, "
            "customer-support automation, low-code/no-code implementation, and financial/trading "
            "operations automation: trading infrastructure, market data, risk monitoring, "
            "portfolio reporting, PnL/fee reconciliation, broker/exchange integrations, "
            "and research pipelines. The person also has a strong finance and capital-markets "
            "background and fits finance operations, treasury, settlement, reconciliation, "
            "compliance, fintech, payments, trading support, middle/back office, risk, and "
            "investment operations roles. The person has 15+ years in trading, investments, "
            "portfolio management, and capital markets, so finance and trading operations "
            "roles are a real fit, not just automation. The person is NOT a traditional "
            "software engineer, frontend developer, ML researcher, or security specialist.\n"
            "Best matches: freelance, contract, remote, consultant, implementation, "
            "workflow automation, AI operations, LLM workflow, chatbot, integration, "
            "scraping, data automation, financial operations, trading operations, treasury, "
            "fintech, payments, compliance, risk, and practical SaaS/MVP work.\n"
            "Finance scoring guide (use these bands, do not auto-boost on the word AI):\n"
            "- score 8-10: the profile's core craft: n8n/Make/Zapier workflow automation, AI agents, "
            "LLM integrations, Telegram bots, scraping and data pipelines, delivered as freelance, "
            "contract or remote projects. These are the best matches.\n"
            "- score 6-8: finance/trading OPERATIONS roles — trading operations, treasury, "
            "settlement, reconciliation, payments operations, compliance, risk operations, "
            "fintech operations, market data, broker/exchange operations, trading support, "
            "middle/back office, trade settlement.\n"
            "- score 5-6: Financial Analyst, Trading Assistant, Trust Operations Associate, "
            "and similar hands-on analyst roles that fit a trading/investment background.\n"
            "- score 4-5: Portfolio Manager, Credit Analyst, and other senior/strategy finance "
            "roles where the person is a partial fit.\n"
            "Score 0-2 for sales, marketing, growth, customer success/support, legal, "
            "design, video, social media, security, pure frontend/mobile, ML research, "
            "data science, Solidity/Rust engineering, tutoring, or roles requiring "
            "independent production coding as the main responsibility. Also score LOW for "
            "senior/lead/staff/manager roles and office or hybrid roles. Do not raise a "
            "score merely because the description contains the words AI, API, crypto, or automation.\n"
            "HARD EXCLUSIONS — ALWAYS set score 0 and verdict \"no\": pure accounting/bookkeeping "
            "roles (Accountant, Bookkeeper, Controller, Accounts Payable/Receivable, Payroll, Audit, "
            "Financial Accountant, Tax Accounting) even if they mention automation; and roles that "
            "are primarily hands-on software engineering in a specific stack (Shopify development, "
            "Node.js, TypeScript, React, Django, FastAPI) where the person must personally write "
            "production code. This profile is an AI-automation builder who assembles practical "
            "workflows and integrations, not a full-time accountant and not a stack-focused "
            "software engineer.\n\n"
            "Return ONLY valid JSON. Score is computed by the system from your dimensions, so do not output score.\n"
            "- type: \"client\" | \"job\" | \"partner\"\n"
            "- urgency: \"low\" | \"medium\" | \"high\"\n"
            "- budget_indicated: true/false\n"
            "- requirements: array (up to 8) of {\"text\": short requirement, \"status\": \"demonstrated\" | \"transferable\" | \"missing\" | \"contradicted\", \"essential\": true or false, \"evidence\": exact phrase copied from the description when demonstrated or transferable, else empty}\n"
            "- gates: {\"direction\": \"pass\"|\"flag\"|\"fail\", \"constraints\": \"pass\"|\"flag\"|\"fail\", \"eligibility\": \"pass\"|\"flag\"|\"fail\"}\n"
            "- dimensions: {\"direction\": 0-100, \"capability\": 0-100, \"scope\": 0-100, \"preferences\": 0-100}\n"
            "- matched_aspects: list of short strings\n"
            "- reason: one short sentence (max 7 words)\n"
            "- risk: one short string (biggest mismatch or gap)\n"
            "Evidence rules: copy the exact phrase from the description, never paraphrase, and keep each quote under 12 words. If no exact phrase exists, status must be missing and evidence empty.\n"
            "Gate rules: direction checks whether the remit matches the profile two tracks (AI automation, finance and trading operations). constraints checks remote location and stated pay (fail when hourly pay is below 10 USD, a fixed project is below 200 USD, or the role is onsite or hybrid). eligibility checks seniority and hard requirements the person cannot meet.\n"
            "Dimension rules: direction is fit of the work itself; capability is proven ability from the profile; scope is size and seniority match; preferences are remote work, freelance or contract, no heavy production coding, no accounting.\n\n"
            + (senior_rule if not allow_senior else "")
            + "Start your reply with { and end with }. No prose before or after the JSON. If the lead is unrelated, set all dimensions to 0 and gates.eligibility to fail."
        )
    else:
        model_prompt = prompt

    raw = llm_complete(model_prompt, text, max_tokens=900, temperature=0.1, timeout=35, json_mode=True, tier="bulk")
    if raw is None:
        return keyword_score(text)
    try:
        data = extract_json(raw)
    except json.JSONDecodeError:
        print(f"  [WARN] LLM bad JSON: {raw[:200]}", flush=True)
        # A free model answered with garbage: retry once on the stronger model
        # before falling back to the keyword score.
        raw = llm_complete(
            model_prompt, text, max_tokens=900, temperature=0.1, timeout=45,
            json_mode=True, tier="escalate",
        )
        try:
            data = extract_json(raw) if raw else None
        except json.JSONDecodeError:
            data = None
        if data is None:
            return keyword_score(text)
    data.setdefault("type", "job")
    data.setdefault("urgency", "low")
    data.setdefault("budget_indicated", False)
    data.setdefault("matched_aspects", [])
    data.setdefault("reason", "")
    data.setdefault("risk", "")

    desc_norm = re.sub(r"\s+", " ", description or "").strip().lower()
    reqs = []
    for item in (data.get("requirements") or []):
        if isinstance(item, str):
            reqs.append({"text": item[:160], "status": "missing", "evidence": ""})
            continue
        if not isinstance(item, dict):
            continue
        status = str(item.get("status", "missing")).lower()
        if status not in ("demonstrated", "transferable", "missing", "contradicted"):
            status = "missing"
        ev = str(item.get("evidence", "") or "").strip()
        if status in ("demonstrated", "transferable"):
            ev_norm = re.sub(r"\s+", " ", ev).lower()
            if not ev_norm or ev_norm not in desc_norm:
                status = "uncited"
        reqs.append({"text": str(item.get("text", ""))[:160], "status": status, "essential": bool(item.get("essential", False)), "evidence": ev[:200]})
    data["requirements"] = reqs[:8]

    raw_gates = data.get("gates") or {}
    gates = {}
    for name in ("direction", "constraints", "eligibility"):
        v = str(raw_gates.get(name, "pass")).lower()
        gates[name] = v if v in ("pass", "flag", "fail") else "flag"

    raw_dims = data.get("dimensions") or {}
    dims = {}
    for name in ("direction", "capability", "scope", "preferences"):
        try:
            dims[name] = max(0, min(int(round(float(raw_dims.get(name, 0)))), 100))
        except Exception:
            dims[name] = 0

    fit = int(round(0.30 * dims["direction"] + 0.25 * dims["capability"]
                    + 0.15 * dims["scope"] + 0.30 * dims["preferences"]))
    if fit >= 75:
        band = "strong"
    elif fit >= 60:
        band = "good"
    elif fit >= 45:
        band = "moderate"
    elif fit >= 30:
        band = "weak"
    else:
        band = "poor"

    contradicted = any(r["status"] == "contradicted" and r.get("essential") for r in reqs)
    missing = any(r["status"] == "missing" and r.get("essential") for r in reqs)
    uncited = sum(1 for r in reqs if r["status"] == "uncited")
    gate_fail = any(v == "fail" for v in gates.values())
    gate_flag = any(v == "flag" for v in gates.values())

    if gate_fail or contradicted:
        decision = "skip"
    elif gate_flag or uncited or (missing and fit < 75):
        decision = "clarify"
    elif fit >= 60:
        decision = "recommend"
    else:
        decision = "skip"

    data["gates"] = gates
    data["dimensions"] = dims
    data["fit"] = fit
    data["band"] = band
    data["decision"] = decision
    data["uncited"] = uncited
    data["verdict"] = "fit" if decision == "recommend" else ("partial" if decision == "clarify" else "no")
    data["score"] = round(fit / 10.0, 1)
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
                leads.append({"title": title, "url": url, "source": "Hacker News",
                              "posted_at": parse_lead_date(hit.get("created_at"))})
            # Get the top-level comments for each hiring post (these are the actual jobs)
            _time.sleep(1)
            item_raw = fetch_url(
                f"https://hn.algolia.com/api/v1/items/{hit.get('objectID', '')}"
            )
            if item_raw:
                try:
                    item_data = json.loads(item_raw)
                    for child in item_data.get("children", []):
                        if child.get("deleted") or child.get("dead"):
                            continue
                        comment_text = (child.get("text", "") or "")[:200]
                        comment_text = re.sub(r'<[^>]+>', '', comment_text).strip()
                        lower_comment = comment_text.lower()
                        # HN hiring threads also attract self-promotional
                        # candidate profiles; do not treat those as vacancies.
                        if ("technologies:" in lower_comment and "we are hiring" not in lower_comment
                                and "we're hiring" not in lower_comment):
                            continue
                        if any(marker in lower_comment for marker in (
                            "looking for a role", "seeking a role", "available for hire",
                            "open to work", "who wants to be hired",
                        )):
                            continue
                        if comment_text:
                            leads.append({
                                "title": comment_text,
                                "url": f"https://news.ycombinator.com/item?id={child.get('id', '')}",
                                "source": "Hacker News",
                                "posted_at": parse_lead_date(child.get("created_at")),
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
        for job in data[1:101] if isinstance(data, list) else []:  # [0] is the legal notice
            if not isinstance(job, dict):
                continue
            title = job.get("position", "")
            url = job.get("url", "")
            if not title:
                continue
            desc = re.sub(r"<[^>]+>", " ", str(job.get("description", "") or ""))
            desc = re.sub(r"\s+", " ", desc).strip()[:800]
            company = str(job.get("company", "") or "").strip()
            location = str(job.get("location", "") or "").strip()
            tags = ", ".join(str(t) for t in (job.get("tags") or [])[:12])
            parts = []
            if company:
                parts.append(f"Company: {company}")
            if location:
                parts.append(f"Location: {location}")
            if tags:
                parts.append("Tags: " + tags)
            if desc:
                parts.append(desc)
            lead = {"title": title, "url": url, "source": "RemoteOK",
                    "description": " ".join(parts)[:800]}
            apply_url = job.get("apply_url", "")
            if apply_url:
                lead["apply_links"] = [apply_url]
            date = job.get("date") or job.get("epoch") or job.get("last_updated")
            pa = parse_lead_date(date)
            if pa is not None:
                lead["posted_at"] = pa
            leads.append(lead)
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
                leads.append({"title": title, "url": url, "source": "Remotive",
                              "posted_at": parse_lead_date(job.get("publication_date"))})
    except Exception as e:
        print(f"  [WARN] Remotive error: {e}")
    print(f"  {len(leads)} leads")
    return leads


def parse_wwr():
    print("[WeWorkRemotely] Fetching RSS...")
    feeds = [
        "https://weworkremotely.com/remote-jobs.rss",
        "https://weworkremotely.com/categories/remote-programming-jobs.rss",
        "https://weworkremotely.com/categories/remote-devops-sysadmin-jobs.rss",
        "https://weworkremotely.com/categories/remote-management-and-finance-jobs.rss",
        "https://weworkremotely.com/categories/remote-product-jobs.rss",
        "https://weworkremotely.com/categories/remote-customer-support-jobs.rss",
    ]
    leads = []
    seen_urls = set()
    for feed in feeds:
        raw = fetch_url(feed, timeout=20)
        if not raw:
            continue
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
                if title and url and url not in seen_urls:
                    seen_urls.add(url)
                    lead = {"title": title[:200], "url": url, "source": "WeWorkRemotely",
                            "description": (desc or "")[:800],
                            "posted_at": parse_lead_date(child("pubDate"))}
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
                              "description": desc[:800],
                              "posted_at": parse_lead_date(job.get("pubDate"))})
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


def _public_card_text(raw, marker, limit=1200):
    """Extract a small text window around a public job-card marker."""
    pos = raw.find(marker)
    if pos < 0:
        return ""
    chunk = raw[max(0, pos - 400):pos + limit]
    text = re.sub(r"<script.*?</script>|<style.*?</style>", " ", chunk, flags=re.I | re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", html.unescape(text)).strip()[:1000]


def _public_job_cards(raw, pattern, base_url, source, pages=1):
    """Parse simple public HTML job cards without login or API credentials."""
    leads = []
    seen = set()
    for href, title_raw in re.findall(pattern, raw, re.I | re.S):
        title = re.sub(r"<[^>]+>", " ", html.unescape(title_raw))
        title = re.sub(r"\s+", " ", title).strip()
        if not title or len(title) < 5:
            continue
        url = href if href.startswith("http") else base_url.rstrip("/") + "/" + href.lstrip("/")
        if url in seen or title.lower() in {"open & apply", "view job", "jobs feed", "next"}:
            continue
        seen.add(url)
        context = _public_card_text(raw, href)
        lead = {"title": title[:200], "url": url, "source": source,
                "description": context[:1000]}
        posted = age_ago_epoch(context)
        if posted is not None:
            lead["posted_at"] = posted
        leads.append(lead)
    return leads


def _provider_listing(lead):
    """Detect public self-promotion cards rather than client requests."""
    text = f"{lead.get('title', '')} {lead.get('description', '')}".lower()
    return any(marker in text for marker in (
        "for hire", "looking for remote opportunities", "looking for opportunities",
        "available now", "available for remote", "available for contracts",
        "ai engineer available", "available for projects", "specialist for hire", "offering assistance",
        "available for freelance", "freelance projects available", "taking on freelance",
        "open to freelance", "freelance work", "seeking freelance",
        "free or low-cost", "portfolio building", "build our portfolio", "mentor",
        "business/sales partner", "remote opportunities", "my tech stack", "what i build",
        "i specialize in", "i build production-ready", "care plan",
        "what i do", "i'm available", "i am available", "available for full-time",
        "available for contract", "available for hire", "hire me", "not hiring",
        "looking for a job", "open to work", "open for work", "i provide white-label",
        "white-label n8n", "freelancer available", "my portfolio",
    ))


def parse_n8n_community_jobs():
    """Official n8n Community Jobs category via public RSS."""
    print("[n8n Community] Fetching Jobs RSS...")
    raw = fetch_url("https://community.n8n.io/c/jobs/13.rss", timeout=20)
    if not raw:
        return []
    leads = []
    try:
        import xml.etree.ElementTree as ET
        root = ET.fromstring(raw)
        for item in root.findall(".//item"):
            def child(tag):
                node = item.find(tag)
                return (node.text or "").strip() if node is not None and node.text else ""
            title = child("title")
            url = child("link")
            desc = re.sub(r"<[^>]+>", " ", html.unescape(child("description")))
            desc = re.sub(r"\s+", " ", desc).strip()[:1200]
            lower = f"{title} {desc}".lower()
            if not title or not url:
                continue
            if any(x in lower for x in ("[for hire]", "for hire", "available for hire", "looking for opportunities", "looking for remote opportunities")):
                continue
            if _provider_listing({"title": title, "description": desc}):
                continue
            if not any(x in lower for x in ("hiring", "looking for", "need someone", "willing to pay", "paid", "seeking")):
                continue
            lead = {"title": title[:200], "url": url, "source": "n8n Community",
                    "description": desc}
            posted = parse_lead_date(child("pubDate"))
            if posted is not None:
                lead["posted_at"] = posted
            leads.append(lead)
    except Exception as e:
        print(f"  [WARN] n8n Community RSS error ({type(e).__name__})")
    print(f"  {len(leads)} client/project leads")
    return leads[:80]


def parse_n8ndevs():
    print("[n8n Devs] Fetching public jobs feed...")
    leads = []
    for page in range(1, 3):
        raw = fetch_url("https://n8ndevs.com/jobs" + (f"?page={page}" if page > 1 else ""), timeout=20)
        if not raw:
            continue
        page_leads = _public_job_cards(
            raw,
            r'href="([^"?#]*?/jobs/[^"?#]+)"[^>]*>(.*?)</a>',
            "https://n8ndevs.com", "n8n Devs",
        )
        client_markers = ("needed", "looking for", "hiring", "wanted", "seeking", "project")
        leads.extend(
            lead for lead in page_leads
            if not _provider_listing(lead)
            and any(marker in lead.get("title", "").lower() for marker in client_markers)
        )
    unique = {lead["url"]: lead for lead in leads}
    print(f"  {len(unique)} public automation listings")
    return list(unique.values())[:80]


def parse_peopleperhour():
    print("[PeoplePerHour] Fetching public automation projects...")
    leads = []
    for page in range(1, 3):
        raw = fetch_url(
            "https://www.peopleperhour.com/freelance-jobs/technology-programming/programming-coding"
            + (f"?page={page}" if page > 1 else ""), timeout=20
        )
        if not raw:
            continue
        leads.extend(_public_job_cards(
            raw,
            r'href="([^"?#]*?/freelance-jobs/technology-programming/programming-coding/[^"?#]+)"[^>]*>(.*?)</a>',
            "https://www.peopleperhour.com", "PeoplePerHour",
        ))
    unique = {lead["url"]: lead for lead in leads}
    print(f"  {len(unique)} public freelance projects")
    return list(unique.values())[:80]


def parse_remoteai():
    print("[RemoteAI] Fetching Automation & AI Workflow jobs...")
    raw = fetch_url("https://remoteai.io/v2/jobs/automation-workflows", timeout=20)
    if not raw:
        return []
    leads = _public_job_cards(
        raw,
        r'href="(/v2/jobs/[^"?#]+)"[^>]*>(.*?)</a>',
        "https://remoteai.io", "RemoteAI",
    )
    print(f"  {len(leads)} AI workflow listings")
    return leads[:80]


def parse_automationroles():
    print("[AutomationRoles.ai] Fetching public AI automation jobs...")
    raw = fetch_url("https://automationroles.ai/jobs", timeout=20)
    if not raw:
        return []
    leads = _public_job_cards(
        raw,
        r'href="(/jobs/[^"?#]+)"[^>]*>(.*?)</a>',
        "https://automationroles.ai", "AutomationRoles.ai",
    )
    print(f"  {len(leads)} AI automation listings")
    return leads[:80]


def _crawl_spa(url, wait_timeout=40):
    """Render a JS-heavy page with a headless browser and return its markdown."""
    try:
        import asyncio
        from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig

        async def _run():
            async with AsyncWebCrawler(config=BrowserConfig(headless=True, verbose=False)) as crawler:
                result = await crawler.arun(
                    url=url,
                    config=CrawlerRunConfig(wait_until="networkidle", page_timeout=wait_timeout * 1000),
                )
                return (result.markdown or ""), result.status_code

        return asyncio.run(_run())
    except Exception as e:
        print(f"  [WARN] crawl4ai failed for {url} ({type(e).__name__})")
        return "", None


def parse_dynamitejobs():
    """DynamiteJobs remote fintech/finance jobs (SPA rendered via headless browser)."""
    print("[DynamiteJobs] Fetching remote finance jobs (browser)...")
    leads = []
    seen = set()
    for category in ("remote-finance-accounting-jobs", "remote-management-operations-jobs"):
        md, status = _crawl_spa(f"https://dynamitejobs.com/category/{category}")
        if not md:
            continue
        pattern = re.compile(r'\[([^\]]{5,110})\]\((https://dynamitejobs\.com/company/[^/]+/remote-job/[^)]+)\)')
        for title, url in pattern.findall(md):
            title = re.sub(r"\s+", " ", title).strip()
            if not title or url in seen:
                continue
            seen.add(url)
            leads.append({"title": title[:200], "url": url, "source": "DynamiteJobs"})
    print(f"  {len(leads)} finance/operations listings")
    return leads[:80]


def parse_efinancialcareers():
    """eFinancialCareers finance jobs (SPA + anti-bot, rendered via headless browser)."""
    print("[eFinancialCareers] Fetching finance jobs (browser)...")
    md, status = _crawl_spa("https://www.efinancialcareers.com/jobs")
    if not md:
        return []
    leads = []
    seen = set()
    for title, url in re.findall(r'\[([^\]]{5,120})\]\((https://www\.efinancialcareers\.com/jobs-[^)]+)\)', md):
        title = re.sub(r"\s+", " ", title).strip()
        if not title or url in seen:
            continue
        seen.add(url)
        leads.append({"title": title[:200], "url": url, "source": "eFinancialCareers"})
    remote = [l for l in leads if "remote" in (l["title"] + " " + l["url"]).lower()]
    print(f"  {len(remote)} remote of {len(leads)} finance listings")
    return remote[:40]


def parse_remotive():
    print("[Remotive] Fetching RSS...")
    raw = fetch_url("https://remotive.com/remote-jobs/feed", timeout=25)
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
            url = child("link")
            if not title or not url:
                continue
            desc = re.sub(r"<[^>]+>", " ", html.unescape(child("description")))
            desc = re.sub(r"\s+", " ", desc).strip()[:1200]
            lead = {"title": title[:200], "url": url, "source": "Remotive", "description": desc}
            posted = parse_lead_date(child("pubDate"))
            if posted is not None:
                lead["posted_at"] = posted
            leads.append(lead)
    except Exception as e:
        print(f"  [WARN] Remotive RSS error: {e}")
    print(f"  {len(leads)} remote jobs")
    return leads[:60]


def parse_workingnomads():
    print("[Working Nomads] Fetching API...")
    raw = fetch_url("https://www.workingnomads.com/api/exposed_jobs/", timeout=25)
    if not raw:
        return []
    leads = []
    try:
        data = json.loads(raw)
        for job in data[:150]:
            title = job.get("title", "")
            url = job.get("url", "")
            if not title or not url:
                continue
            desc = re.sub(r"<[^>]+>", " ", html.unescape(str(job.get("description", ""))))
            desc = re.sub(r"\s+", " ", desc).strip()[:1200]
            lead = {"title": title[:200], "url": url, "source": "WorkingNomads", "description": desc}
            posted = parse_lead_date(job.get("pub_date") or job.get("date"))
            if posted is not None:
                lead["posted_at"] = posted
            leads.append(lead)
    except Exception as e:
        print(f"  [WARN] Working Nomads error: {e}")
    print(f"  {len(leads)} remote jobs")
    return leads[:60]


def parse_nodesk():
    print("[NoDesk] Fetching RSS...")
    raw = fetch_url("https://nodesk.co/remote-jobs/index.xml", timeout=25)
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
            url = child("link")
            if not title or not url:
                continue
            desc = re.sub(r"<[^>]+>", " ", html.unescape(child("description")))
            desc = re.sub(r"\s+", " ", desc).strip()[:1200]
            lead = {"title": title[:200], "url": url, "source": "NoDesk", "description": desc}
            posted = parse_lead_date(child("pubDate"))
            if posted is not None:
                lead["posted_at"] = posted
            leads.append(lead)
    except Exception as e:
        print(f"  [WARN] NoDesk RSS error: {e}")
    print(f"  {len(leads)} remote jobs")
    return leads[:60]


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
                              "description": desc[:800],
                              "posted_at": parse_lead_date(job.get("pubDate"))})
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
                de = job.get("date_epoch")
                if isinstance(de, (int, float)):
                    lead["posted_at"] = de
                leads.append(lead)
        except Exception as e:
            print(f"  [WARN] Web3Career tag={tag} error: {e}")
    print(f"  {len(leads)} leads")
    return leads


def parse_solana_getro():
    """Solana job board (jobs.solana.com, powered by Getro)."""
    print("[Solana] Fetching from Getro API...")
    leads = []
    try:
        url = "https://api.getro.com/api/v2/collections/858/search/jobs"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/125.0 Safari/537.36",
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Origin": "https://jobs.solana.com",
            "Referer": "https://jobs.solana.com/",
        }
        body = {"hits_per_page": 500, "page": 0, "filters": "", "query": ""}
        resp = requests.post(url, headers=headers, json=body, timeout=30)
        resp.raise_for_status()
        jobs = resp.json().get("results", {}).get("jobs", [])
        for job in jobs:
            if not isinstance(job, dict):
                continue
            title = str(job.get("title", "") or "").strip()
            url = str(job.get("url", "") or "").strip()
            org_obj = job.get("organization")
            org = org_obj.get("name", "") if isinstance(org_obj, dict) else (str(org_obj) if org_obj else "")
            if not title or not url:
                continue
            skills = job.get("skills") or []
            location = ", ".join(job.get("searchable_locations") or [])[:150]
            desc = str(job.get("description") or "")
            if desc:
                desc = re.sub(r"<[^>]+>", " ", desc)
                desc = re.sub(r"\s+", " ", desc).strip()[:800]
            parts = [f"Company: {org}", f"Location: {location}"]
            if skills:
                parts.append("Skills: " + ", ".join(skills[:12]))
            if desc:
                parts.append(desc)
            lead = {
                "title": title[:200],
                "url": url,
                "source": "Solana",
                "description": " ".join(parts)[:800],
                "apply_links": [url],
                "company": org,
            }
            ca = job.get("created_at")
            if isinstance(ca, (int, float)):
                lead["posted_at"] = ca
            leads.append(lead)
    except Exception as e:
        print(f"  [WARN] Solana Getro error: {e}")
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
                    leads.append({"title": title, "url": url, "source": "Reddit",
                                  "posted_at": parse_lead_date(post.get("created_utc"))})
    except Exception as e:
        print(f"  [WARN] Reddit parse error: {e}")
    print(f"  {len(leads)} leads")
    return leads


def parse_telegram_sources():
    if not TG_API_ID or not TG_API_HASH or not os.path.exists(TG_SESSION):
        print("[Telegram] No authorized user session — using public web fallback")
        return _parse_telegram_web()

    # A bot token is for delivery only. Reading channel history requires the
    # authorized Telethon user session stored in the ignored *.session file.
    async def _fetch():
        client = TelegramClient(TG_SESSION, TG_API_ID, TG_API_HASH)
        try:
            await client.connect()
            if not await client.is_user_authorized():
                print("  [Telegram] User session is not authorized — web fallback")
                await client.disconnect()
                return None
        except Exception as e:
            print(f"  [WARN] Telegram session unavailable ({type(e).__name__}) — web fallback")
            await client.disconnect()
            return None

        leads = []
        for ch in TELEGRAM_SOURCES:
            try:
                entity = await client.get_entity(ch["name"])
                for msg in await client.get_messages(entity, limit=30):
                    if msg.message:
                        text = msg.message.strip()
                        if not _telegram_job_candidate(text):
                            continue
                        leads.append({
                            "title": _telegram_title(text),
                            "description": text[:1200],
                            "url": f"https://t.me/{ch['name']}/{msg.id}",
                            "source": f"Telegram @{ch['name']}",
                            "posted_at": msg.date.timestamp() if msg.date else None,
                        })
                n = sum(1 for l in leads if l.get("source") == f"Telegram @{ch['name']}")
                print(f"  [{ch['name']}] {n} job messages (user session)")
            except Exception as e:
                print(f"  [WARN] @{ch['name']} failed ({type(e).__name__})")
        await client.disconnect()
        return leads

    try:
        result = asyncio.run(_fetch())
        if result is None:
            return _parse_telegram_web()
        return result
    except Exception as e:
        print(f"  [WARN] Telegram parser error ({type(e).__name__}) — web fallback")
        return _parse_telegram_web()


def _telegram_job_candidate(text):
    """Keep likely job/project posts and discard common channel noise."""
    normalized = re.sub(r"\s+", " ", text or "").strip().lower()
    if not normalized or any(word in normalized for word in TELEGRAM_NOISE):
        return False
    return any(word in normalized for word in TELEGRAM_JOB_HINTS)


def _telegram_title(text):
    """Use the first meaningful line as title while retaining full description."""
    lines = [re.sub(r"\s+", " ", line).strip() for line in (text or "").splitlines()]
    lines = [line for line in lines if line]
    return (lines[0] if lines else text or "Telegram job")[:200]


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
            text = html.unescape(re.sub(r"\s+", " ", text)).strip()
            if text and not skip_patterns.match(text) and _telegram_job_candidate(text):
                msg_url = msg_links[idx] if idx < len(msg_links) else f"https://t.me/{ch['name']}"
                date_match = re.search(r'<time[^>]+datetime="([^"]+)"', block, re.I)
                leads.append({
                    "title": _telegram_title(text),
                    "description": text[:1200],
                    "url": msg_url,
                    "source": f"Telegram @{ch['name']}",
                    "posted_at": parse_lead_date(date_match.group(1)) if date_match else None,
                })
        n = sum(1 for l in leads if l.get("source") == f"Telegram @{ch['name']}")
        print(f"  [{ch['name']}] {n} job messages (web)")

    # Cross-posts often have different Telegram URLs but identical text.
    unique = []
    seen = set()
    for lead in leads:
        key = stable_hash(re.sub(r"\W+", " ", lead.get("description", "").lower()).strip())
        if key in seen:
            continue
        seen.add(key)
        unique.append(lead)
    print(f"[Telegram] Kept {len(unique)} job messages; removed {len(leads) - len(unique)} cross-post duplicates")
    return unique


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
                   (title, source, url, score, fit, type, urgency, budget, matched_aspects,
                    reason, description, posted_at, gates, evidence)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    r["title"],
                    r["source"],
                    r["url"],
                    r.get("score", 0),
                    r.get("fit"),
                    r.get("type", "job"),
                    r.get("urgency", "low"),
                    json.dumps(r.get("budget_indicated", False)),
                    json.dumps(r.get("matched_aspects", [])),
                    r.get("reason", ""),
                    r.get("description", ""),
                    r.get("posted_at"),
                    json.dumps(r.get("gates", {})),
                    json.dumps(r.get("requirements", [])),
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


def send_tg_message(text, reply_markup=None):
    if not TG_BOT_TOKEN or not OWNER_CHAT_ID:
        return
    try:
        url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
        payload = {
            "chat_id": OWNER_CHAT_ID,
            "text": text[:4000],
            "parse_mode": "HTML",
            "disable_web_page_preview": True
        }
        if reply_markup:
            payload["reply_markup"] = reply_markup
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"  [WARN] TG send failed: {e}")
    for tok, chat in GUEST_BOTS:
        try:
            url = f"https://api.telegram.org/bot{tok}/sendMessage"
            payload = {
                "chat_id": chat,
                "text": text[:4000],
                "parse_mode": "HTML",
                "disable_web_page_preview": True
            }
            if reply_markup:
                payload["reply_markup"] = reply_markup
            requests.post(url, json=payload, timeout=10)
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


def send_tg_message_to(bot_token, chat_id, text, reply_markup=None):
    try:
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": text[:4000],
            "parse_mode": "HTML",
            "disable_web_page_preview": True
        }
        if reply_markup:
            payload["reply_markup"] = reply_markup
        r = requests.post(url, json=payload, timeout=10)
        return r.status_code == 200
    except Exception as e:
        print(f"  [WARN] TG send to guest failed: {e}", flush=True)


def _lead_url_from_callback(token):
    conn = sqlite3.connect(DB_PATH)
    try:
        for (url,) in conn.execute("SELECT url FROM leads WHERE url IS NOT NULL"):
            if stable_hash(url) == token:
                return url
    finally:
        conn.close()
    return None


def _answer_callback(callback_id, text):
    if not TG_BOT_TOKEN:
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{TG_BOT_TOKEN}/answerCallbackQuery",
            json={"callback_query_id": callback_id, "text": text, "show_alert": False},
            timeout=10,
        )
    except Exception as e:
        print(f"  [WARN] callback answer failed ({type(e).__name__})", flush=True)


def _clear_callback_buttons(callback):
    message = callback.get("message") or {}
    chat = message.get("chat") or {}
    message_id = message.get("message_id")
    if not TG_BOT_TOKEN or not chat.get("id") or not message_id:
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{TG_BOT_TOKEN}/editMessageReplyMarkup",
            json={"chat_id": chat["id"], "message_id": message_id, "reply_markup": {"inline_keyboard": []}},
            timeout=10,
        )
    except Exception as e:
        print(f"  [WARN] callback buttons clear failed ({type(e).__name__})", flush=True)
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

    send_fn = lambda t, reply_markup=None: send_tg_message_to(
        guest["bot_token"], guest["chat_id"], t, reply_markup=reply_markup
    )
    leads_to_tg(fresh, send_fn=send_fn, with_actions=False)
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
        "SELECT title, source, url, score, matched_aspects, reason, description, posted_at "
        "FROM leads WHERE sent=1 AND score >= 6"
    ).fetchall()
    q = []
    for title, source, url, score, aspects, reason, desc, posted_at in rows:
        if not url or url in oc:
            continue
        lead = {
            "title": title,
            "source": source,
            "url": url,
            "score": score,
            "matched_aspects": json.loads(aspects) if aspects else [],
            "reason": reason or "",
            "description": desc or "",
            "posted_at": posted_at,
        }
        if not lead_fresh(lead):
            print(f"  [Queue] Dropped old lead: {title[:60]}", flush=True)
            continue
        q.append(lead)
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
            "You are a busy AI automation and financial-operations product builder. Ideal work includes "
            "Telegram bots, trading operations automation, market-data and risk monitoring, portfolio/PnL "
            "reporting, broker/exchange integrations, n8n/LLM workflows, e-commerce automation, payment "
            "integrations, lead generation, data pipelines, MVPs, and SaaS tools. "
            "For each lead below decide: 'today' = strong match, reply ASAP; 'week' = decent, reply within a week; "
            "'skip' = weak, spammy, senior role, or not a fit.\n\n"
            "Return ONLY a JSON object mapping number to tag, e.g. {\"1\": \"today\", \"2\": \"skip\"}.\n\n"
            + "\n".join(lines)
        )
        raw = llm_complete(
            "You classify freelance job leads into today/week/skip.",
            prompt, max_tokens=800, temperature=0.1, timeout=45, tier="quality",
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


def send_backlog(conn, limit=30, chunk=10):
    """Compact ranked list of pending leads (sent, score>=6, no outcome yet)."""
    q = build_queue(conn)
    if not q:
        send_tg_message("📭 Бэклог пуст: нет необработанных лидов (score ≥ 6).")
        return
    q = q[:limit]
    for start in range(0, len(q), chunk):
        part = q[start:start + chunk]
        if start == 0:
            msg = f"📋 <b>Бэклог</b> · {len(q)} лидов без отклика\n" + "─" * 25
        else:
            msg = f"📋 <b>Продолжение</b> · {start + 1}–{start + len(part)}\n" + "─" * 25
        for i, l in enumerate(part, start + 1):
            score = l.get("score", 0)
            source = html.escape(l.get("source", "?"))
            title = html.escape(l["title"][:85].replace("#", ""))
            budget = html.escape(extract_budget((l.get("title") or "") + " " + (l.get("description") or "")))
            dstr = ""
            if l.get("posted_at"):
                try:
                    dstr = datetime.fromtimestamp(float(l["posted_at"])).strftime("%d.%m")
                except Exception:
                    dstr = ""
            msg += f"\n\n<b>{i}. ⭐{score}/10</b> [{source}] {title}"
            bits = []
            if budget:
                bits.append(f"💰 {budget}")
            if dstr:
                bits.append(f"🕐 {dstr}")
            if bits:
                msg += "\n" + "   ".join(bits)
            if l.get("reason"):
                msg += f"\n💬 {html.escape(l['reason'][:100])}"
            if l.get("url"):
                msg += f"\n🔗 <a href=\"{html.escape(l['url'])}\">{short_url(l['url'])}</a>"
        send_tg_message(msg[:3900])
        time.sleep(0.5)


DIGEST_STATE = os.path.join(DATA_DIR, "digest_seen.json")


def send_daily_digest(conn, limit=20):
    """Compact daily digest: pending leads scored 6-7.9 (one line each), sent once."""
    seen = set()
    if os.path.exists(DIGEST_STATE):
        try:
            seen = set(json.load(open(DIGEST_STATE)))
        except Exception:
            seen = set()
    oc = load_outcomes()
    rows = conn.execute(
        "SELECT title, source, url, score, description FROM leads "
        "WHERE sent=1 AND score >= 6 AND score < 8 ORDER BY score DESC, created_at DESC"
    ).fetchall()
    picks = [r for r in rows if r[2] and r[2] not in oc and r[2] not in seen][:limit]
    if not picks:
        print("[Digest] nothing new", flush=True)
        return
    included = []
    msg = f"📊 <b>Дайджест лидов</b> · {len(picks)} шт (score 6-7.9)\n" + "─" * 25
    for i, (title, source, url, score, desc) in enumerate(picks, 1):
        t = html.escape((title or "")[:75].replace("#", ""))
        src = html.escape(source or "?")
        budget = extract_budget((title or "") + " " + (desc or ""))
        line = f"\n\n{i}. ⭐<b>{score}</b> [{src}]\n{t}"
        if budget:
            line += f" · 💰{html.escape(budget)}"
        line += f"\n🔗 <a href=\"{html.escape(url)}\">открыть</a>"
        if len(msg) + len(line) > 3800:
            break
        msg += line
        included.append((title, source, url, score, desc))
    send_tg_message(msg[:3900])
    seen.update(r[2] for r in (included or picks[:1]))
    try:
        json.dump(sorted(seen)[-5000:], open(DIGEST_STATE, "w"))
    except Exception as e:
        print(f"[Digest] state save failed: {e}", flush=True)
    print(f"[Digest] sent {len(picks)} leads", flush=True)


def send_digest(conn):
    """Show only leads with a recorded user action, not an old backlog."""
    outcomes = load_outcomes()
    outcomes = {url: status for url, status in outcomes.items()
                if status in {"replied", "called", "paid"}}
    if not outcomes:
        send_tg_message("📭 Пока нет отмеченных действий. Новые лиды приходят автоматически после скана.")
        return
    rows = []
    for url, status in outcomes.items():
        row = conn.execute(
            "SELECT title, source, score, url FROM leads WHERE url=?", (url,)
        ).fetchone()
        if row:
            rows.append((status, row))
    if not rows:
        send_tg_message("📭 Отмеченных лидов пока нет в текущей базе.")
        return
    order = {"paid": 0, "called": 1, "replied": 2, "skipped": 3}
    rows.sort(key=lambda x: (order.get(x[0], 9), -float(x[1][2] or 0)))
    icons = {"paid": "💰", "called": "📞", "replied": "✉️", "skipped": "⏭"}
    lines = [f"📈 <b>Мои действия</b> · {len(rows)} лидов\n" + "─" * 25]
    for status, (title, source, score, url) in rows[:20]:
        lines.append(
            f"\n{icons.get(status, '•')} <b>{html.escape(title[:85])}</b>\n"
            f"   {status} · ⭐{score}/10 · {html.escape(source or '?')}\n"
            f"   🔗 <a href=\"{html.escape(url)}\">открыть</a>"
        )
    if len(rows) > 20:
        lines.append(f"\n… ещё {len(rows) - 20} в истории")
    send_tg_message("\n".join(lines))


AGENT_ENABLED = os.getenv("MCP_AGENT_ENABLED", "true").lower() in ("1", "true", "yes", "on")


def _agent_readonly_connection():
    """Open the LeadHunter database in read-only mode for the text agent."""
    return sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True, timeout=5)


def _agent_get_profile():
    return {"profile": PROFILE_TEXT}


def _agent_search_leads(keywords=None, days=30, limit=5):
    """Read-only search over fresh leads; never changes the database."""
    keywords = [str(k).strip().lower() for k in (keywords or []) if str(k).strip()]
    days = max(1, min(int(days or 30), 30))
    limit = max(1, min(int(limit or 5), 10))
    cutoff = time.time() - days * 86400
    conn = _agent_readonly_connection()
    try:
        clauses = ["posted_at IS NOT NULL", "posted_at >= ?"]
        params = [cutoff]
        if keywords:
            text_parts = []
            for word in keywords[:8]:
                pattern = f"%{word}%"
                text_parts.append("(lower(title) LIKE ? OR lower(description) LIKE ? OR lower(matched_aspects) LIKE ?)")
                params.extend([pattern, pattern, pattern])
            clauses.append("(" + " OR ".join(text_parts) + ")")
        rows = conn.execute(
            "SELECT id,title,source,url,score,reason,matched_aspects,description,posted_at "
            "FROM leads WHERE " + " AND ".join(clauses) +
            " ORDER BY score DESC, posted_at DESC LIMIT ?", params + [limit]
        ).fetchall()
        return [{
            "id": r[0], "title": r[1], "source": r[2], "url": r[3], "score": r[4],
            "reason": r[5] or "", "matched_aspects": json.loads(r[6]) if r[6] else [],
            "description": r[7] or "", "posted_at": r[8],
        } for r in rows]
    finally:
        conn.close()


def _agent_get_lead_details(lead_id):
    conn = _agent_readonly_connection()
    try:
        row = conn.execute(
            "SELECT id,title,source,url,score,reason,matched_aspects,description,posted_at "
            "FROM leads WHERE id=?", (int(lead_id),)
        ).fetchone()
        if not row:
            return None
        return {
            "id": row[0], "title": row[1], "source": row[2], "url": row[3], "score": row[4],
            "reason": row[5] or "", "matched_aspects": json.loads(row[6]) if row[6] else [],
            "description": row[7] or "", "posted_at": row[8],
        }
    finally:
        conn.close()


def _agent_scan_summary():
    conn = _agent_readonly_connection()
    try:
        total = conn.execute("SELECT COUNT(*) FROM leads").fetchone()[0]
        fresh = conn.execute(
            "SELECT COUNT(*) FROM leads WHERE posted_at IS NOT NULL AND posted_at >= ?",
            (time.time() - MAX_LEAD_AGE_DAYS * 86400,)
        ).fetchone()[0]
        high = conn.execute("SELECT COUNT(*) FROM leads WHERE score >= 6").fetchone()[0]
        sent = conn.execute("SELECT COUNT(*) FROM leads WHERE sent=1").fetchone()[0]
        return {"total": total, "fresh_with_date": fresh, "score_6_plus": high, "sent": sent}
    finally:
        conn.close()


def _agent_plan(query):
    """Turn a text request into one safe read-only tool call."""
    system = (
        "You route requests for a read-only lead database. Return ONLY JSON. "
        "Allowed tools: search_leads, get_lead_details, get_scan_summary, get_profile, draft_application. "
        "draft_application only prepares text and never sends it. "
        "For a request for best leads, use search_leads. Extract up to 6 concrete keywords, "
        "days (default 30), limit (default 5), and lead_id when present."
    )
    raw = llm_complete(system, query[:1000], max_tokens=180, temperature=0.1, timeout=20, tier="quality")
    if not raw:
        return {"tool": "search_leads", "keywords": [], "days": 30, "limit": 5}
    try:
        plan = extract_json(raw)
        if plan.get("tool") not in {"search_leads", "get_lead_details", "get_scan_summary", "get_profile", "draft_application"}:
            raise ValueError("unsupported tool")
        return plan
    except Exception:
        return {"tool": "search_leads", "keywords": [], "days": 30, "limit": 5}


def _agent_format_results(leads):
    if not leads:
        return "🔎 Ничего подходящего не найдено за указанный период."
    chunks = [f"🔎 <b>Найдено лидов: {len(leads)}</b>"]
    for i, lead in enumerate(leads, 1):
        aspects = ", ".join(lead.get("matched_aspects", [])[:5])
        chunks.append(
            f"\n<b>{i}. {html.escape(lead['title'][:100])}</b> · ⭐{lead.get('score', 0)}/10\n"
            f"Источник: {html.escape(lead.get('source', '?'))}\n"
            f"Почему: {html.escape(lead.get('reason', '')[:180])}\n"
            + (f"Метки: {html.escape(aspects)}\n" if aspects else "")
            + f"ID: <code>{lead['id']}</code>\n🔗 {html.escape(lead.get('url', ''))}"
        )
    return "\n".join(chunks)[:3900]


def run_agent_query(query):
    """Handle /agent text requests with read-only tools only."""
    if not AGENT_ENABLED:
        return "🧭 Agent mode is disabled."
    query = (query or "").strip()
    if not query:
        return "🧭 Напиши запрос после /agent, например: /agent найди 3 лучших лида за неделю для AI automation"
    plan = _agent_plan(query)
    tool = plan.get("tool")
    try:
        if tool == "search_leads":
            result = _agent_search_leads(plan.get("keywords", []), plan.get("days", 30), plan.get("limit", 5))
            return "🧭 <b>Read-only agent</b>\n" + _agent_format_results(result)
        if tool == "get_lead_details":
            lead = _agent_get_lead_details(plan.get("lead_id"))
            return "🧭 <b>Read-only agent</b>\n" + (_agent_format_results([lead]) if lead else "Лид с таким ID не найден.")
        if tool == "get_scan_summary":
            s = _agent_scan_summary()
            return ("🧭 <b>Scan summary</b>\n"
                    f"Всего: {s['total']}\nСвежих с датой: {s['fresh_with_date']}\n"
                    f"Score 6+: {s['score_6_plus']}\nОтправлено: {s['sent']}")
        if tool == "get_profile":
            return "🧭 <b>Current profile</b>\n" + html.escape(PROFILE_TEXT[:3500])
        if tool == "draft_application":
            lead = _agent_get_lead_details(plan.get("lead_id"))
            if not lead:
                return "Лид с таким ID не найден."
            draft = generate_application(lead, email="onlinebis2016@gmail.com")
            return "🧭 <b>Draft only — not sent</b>\n" + html.escape(draft or "Черновик не сгенерирован.")
    except Exception as e:
        print(f"  [WARN] agent query failed ({type(e).__name__})", flush=True)
        return "⚠️ Agent не смог обработать запрос. Обычная рассылка продолжает работать."
    return "⚠️ Не удалось определить безопасное read-only действие."


def tg_poll_outcomes():
    """Daemon: watch owner's messages in TG.
    - Reply with replied/called/paid -> outcome for that lead.
    - Plain commands: d10 / app N / skip N / next / digest / queue / help.
    - Read-only text agent: /agent <request>.
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
            params = {"timeout": 30, "offset": last_update_id, "allowed_updates": ["message", "callback_query"]}
            r = requests.get(url, params=params, timeout=40)
            data = r.json()
            for upd in data.get("result", []):
                last_update_id = max(last_update_id, upd["update_id"] + 1)
                callback = upd.get("callback_query")
                if callback:
                    callback_chat = str(((callback.get("message") or {}).get("chat") or {}).get("id", ""))
                    if OWNER_CHAT_ID and callback_chat != str(OWNER_CHAT_ID):
                        continue
                    parts = (callback.get("data") or "").split(":")
                    if len(parts) == 3 and parts[0] == "outcome":
                        status, token = parts[1], parts[2]
                        url = _lead_url_from_callback(token)
                        if url and status in {"replied", "skipped"}:
                            record_outcome(url, status)
                            _answer_callback(callback.get("id", ""), "Сохранено")
                            _clear_callback_buttons(callback)
                        else:
                            _answer_callback(callback.get("id", ""), "Лид не найден")
                    continue
                msg = upd.get("message")
                if not msg:
                    continue
                if OWNER_CHAT_ID and str(msg.get("chat", {}).get("id", "")) != str(OWNER_CHAT_ID):
                    continue
                text = (msg.get("text") or "").strip().lower()
                if not text:
                    continue
                reply = msg.get("reply_to_message")

                if text.startswith("/agent") or text.startswith("agent "):
                    query = re.sub(r"^/?agent\s*", "", text, count=1).strip()
                    send_tg_message(run_agent_query(query))
                    continue

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
                if text in ("help", "/help", "помощь", "/start", "start"):
                    send_tg_message(
                        "📖 <b>Основные команды</b>\n"
                        "<code>/backlog</code> — топ необработанных лидов (score ≥ 6)\n"
                        "<code>/funnel</code> — только лиды, где было действие\n"
                        "<code>/agent запрос</code> — спросить AI по базе\n\n"
                        "На сообщение с лидом ответь: <code>replied</code>, <code>called</code> или <code>paid</code>."
                    )
                    continue
                if text in ("digest", "/digest", "/funnel", "funnel", "дайджест"):
                    try:
                        c = sqlite3.connect(DB_PATH)
                        send_digest(c)
                        c.close()
                    except Exception as e:
                        print(f"  [WARN] digest failed: {e}", flush=True)
                        send_tg_message(f"⚠️ digest failed: {e}")
                    continue
                if text in ("backlog", "/backlog", "бэклог"):
                    try:
                        c = sqlite3.connect(DB_PATH)
                        send_backlog(c)
                        c.close()
                    except Exception as e:
                        print(f"  [WARN] backlog failed: {e}", flush=True)
                        send_tg_message(f"⚠️ backlog failed: {e}")
                    continue
                if text in ("queue", "/queue", "очередь"):
                    send_tg_message("📭 Старую очередь не показываю. Необработанные лиды: /backlog. История действий: /funnel")
                    continue
                if text in ("d10", "/d10", "next", "/next") or text.startswith(("app ", "/app ", "skip ", "/skip ")):
                    send_tg_message("📭 Старую очередь отключил. Новые лиды приходят автоматически с draft. История действий: /funnel")
                    continue
        except Exception as e:
            print(f"  [WARN] TG poll error: {e}", flush=True)
            time.sleep(10)
        time.sleep(1)


PROFILE_TEXT = """Andrey Mashkin: AI Automation and Financial Operations Builder, Bangkok (remote worldwide).
- Solo builder with 15+ years in trading and investments across equities, FX, commodities, and crypto.
- Built TradeMind Lite: AI trading journal Telegram bot with crypto payments (Plisio).
- Runs 6 algorithmic trading bots (gold, BTC, oil, altcoins) on a small VPS with zero downtime: self-healing health checks, cron dashboards, instant Telegram alerts.
- DeFi trading infrastructure on Hyperliquid and other top DEXs: partial-close accounting, fees optimization, crash recovery.
- Builds trading-operations automations: market-data pipelines, risk monitoring, portfolio/PnL reporting, fee reconciliation, trade journals, and broker/exchange integrations.
- Finance and capital-markets operations background: treasury, settlement, reconciliation, compliance, payments, trading support, middle/back office, and risk operations.
- Built LeadHunter Pro: profile-matched LLM lead intelligence, data ingestion, freshness filtering, Telegram delivery, and draft workflows.
- Tech: Python, Telegram Bot API, Cloudflare Workers, OpenRouter (various models), n8n, scraping, VPS/Linux, cron, HTML/CSS/JS.
- E-commerce automation: logic, orders, payments.
- Pricing: systems that run without me, priced on value, not hours.
- English: fluent professional; Russian: native.
- Links: LinkedIn linkedin.com/in/andrey-mashkin, GitHub github.com/impowery/leadhunter, project page https://luna56.vercel.app.
- Timezone: Bangkok, UTC+7. Available immediately, remote worldwide.
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
            prompt, max_tokens=250, temperature=0.4, timeout=25, tier="quality",
        )
        if raw:
            return raw[:1500]
    except Exception:
        pass
    return None


KITS_STATE = os.path.join(DATA_DIR, "kits_seen.json")
CV_DOCX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "resume", "Andrey Mashkin CV (updated).docx")
CV_PDF = os.path.join(os.path.dirname(os.path.abspath(__file__)), "resume", "Andrey_Mashkin_CV_EN.pdf")


def send_owner_message(text, reply_markup=None):
    """Send a message to the owner only (skips guest bots)."""
    if not TG_BOT_TOKEN or not OWNER_CHAT_ID:
        return
    try:
        payload = {
            "chat_id": OWNER_CHAT_ID,
            "text": text[:4000],
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        if reply_markup:
            payload["reply_markup"] = reply_markup
        requests.post(
            "https://api.telegram.org/bot" + TG_BOT_TOKEN + "/sendMessage",
            json=payload, timeout=10,
        )
    except Exception as e:
        print("  [WARN] owner send failed: " + str(e), flush=True)


def build_application_kit(lead, email=None):
    """One LLM call: tailored letter plus standard application answers."""
    profile_text = PROFILE_TEXT
    title = lead.get("title", "")
    desc = (lead.get("description") or title)[:1500]
    reqs = lead.get("requirements") or []
    req_lines = "; ".join(
        str(r.get("text", "")) + " (" + str(r.get("status", "")) + ")"
        for r in reqs[:6] if isinstance(r, dict)
    )
    evidence = "; ".join(
        str(r.get("evidence", ""))[:120]
        for r in reqs[:4] if isinstance(r, dict) and r.get("evidence")
    )
    prompt = (
        "Write a job application package for this candidate.\n\n"
        + profile_text + "\n\n"
        + "Job title: " + title + "\n"
        + "Job description: " + desc + "\n"
        + ("Requirements matched: " + req_lines + "\n" if req_lines else "")
        + ("Verbatim evidence from the advert: " + evidence + "\n" if evidence else "")
        + "\nReturn ONLY JSON with keys:\n"
        + "- letter: 110-160 words, first person, specific to this advert, mention 1-2 concrete facts from the profile, no invented experience, no em dashes, end with a short call to action"
        + ((", include the contact email " + email) if email else "") + "\n"
        + "- answers: object with keys availability, timezone, rate, notice, english, links. Each answer under 20 words, honest, based only on the profile. For the answers use these fixed facts: English is fluent professional, timezone is Bangkok UTC+7, availability is immediate, rate is value-based not hourly, links are linkedin.com/in/andrey-mashkin, github.com/impowery/leadhunter and luna56.vercel.app. Do not hedge or say that information is missing.\n"
        + "Start with { and end with }."
    )
    raw = llm_complete(
        "You write concise, specific job application packages and return JSON only.",
        prompt, max_tokens=800, temperature=0.35, timeout=35, json_mode=True, tier="quality",
    )
    kit = {"letter": "", "answers": {}}
    if raw:
        try:
            data = extract_json(raw)
            kit["letter"] = str(data.get("letter", ""))[:2000]
            answers = data.get("answers") or {}
            if isinstance(answers, dict):
                kit["answers"] = {str(k): str(v)[:200] for k, v in answers.items()}
        except Exception:
            kit["letter"] = raw[:1500]
    if not kit["letter"]:
        kit["letter"] = generate_application(lead, email=email) or ""
    return kit


def send_tg_document(path, caption=""):
    if not TG_BOT_TOKEN or not OWNER_CHAT_ID or not os.path.exists(path):
        return False
    try:
        with open(path, "rb") as f:
            requests.post(
                "https://api.telegram.org/bot" + TG_BOT_TOKEN + "/sendDocument",
                data={"chat_id": OWNER_CHAT_ID, "caption": caption[:900], "parse_mode": "HTML"},
                files={"document": (os.path.basename(path), f)},
                timeout=60,
            )
        return True
    except Exception as e:
        print("  [WARN] TG document failed: " + str(e), flush=True)
        return False


def send_application_kits(leads, limit=3, conn=None):
    """Send ready-to-use application packages for the strongest leads."""
    if not leads:
        return 0
    seen = set()
    if os.path.exists(KITS_STATE):
        try:
            seen = set(json.load(open(KITS_STATE)))
        except Exception:
            seen = set()
    picks = []
    for l in sorted(leads, key=lambda x: x.get("fit") or 0, reverse=True):
        if len(picks) >= limit:
            break
        url = l.get("url")
        if not url or url in seen:
            continue
        if (l.get("decision") or "") != "recommend" and float(l.get("fit") or 0) < 60:
            continue
        picks.append(l)
    if not picks:
        return 0
    sent = 0
    for l in picks:
        try:
            kit = build_application_kit(l, email="onlinebis2016@gmail.com")
            if not kit.get("letter"):
                continue
            fit = l.get("fit") or 0
            source = html.escape(l.get("source", "?"))
            title = html.escape((l.get("title") or "")[:90])
            url = html.escape(l.get("url", ""))
            ans = kit.get("answers") or {}
            labels = [("availability", "Доступность"), ("timezone", "Часовой пояс"),
                      ("rate", "Ставка"), ("notice", "Notice"), ("english", "Английский"),
                      ("links", "Ссылки")]
            ans_lines = []
            for key, label in labels:
                if ans.get(key):
                    ans_lines.append("• " + label + ": " + html.escape(str(ans[key])))
            msg = (
                "🎯 <b>Пакет отклика</b> · fit " + str(fit) + "/100\n"
                + "─" * 25 + "\n"
                + "<b>" + title + "</b> · " + source + "\n\n"
                + "📝 <b>Письмо</b>\n<pre>" + html.escape(kit["letter"]) + "</pre>\n"
                + (("\n🗣 <b>Ответы</b>\n" + "\n".join(ans_lines) + "\n") if ans_lines else "")
                + "\n🔗 <a href=\"" + url + "\">открыть вакансию</a>"
            )
            token = stable_hash(l["url"])
            keyboard = [[
                {"text": "✅ Откликнулся", "callback_data": "outcome:replied:" + token},
                {"text": "⏭ Пропустить", "callback_data": "outcome:skipped:" + token},
            ]]
            send_owner_message(msg[:3900], reply_markup={"inline_keyboard": keyboard})
            try:
                if conn is not None:
                    conn.execute(
                        "INSERT OR REPLACE INTO kits (url, letter, answers) VALUES (?, ?, ?)",
                        (l["url"], kit.get("letter", ""), json.dumps(ans)),
                    )
                    conn.commit()
            except Exception as e:
                print("  [WARN] kit store failed: " + str(e), flush=True)
            seen.add(l["url"])
            sent += 1
            time.sleep(0.7)
        except Exception as e:
            print("  [WARN] kit failed: " + str(e), flush=True)
    if sent:
        try:
            json.dump(sorted(seen)[-2000:], open(KITS_STATE, "w"))
        except Exception as e:
            print("  [WARN] kits state save failed: " + str(e), flush=True)
        cv_path = CV_PDF if os.path.exists(CV_PDF) else CV_DOCX
        if os.path.exists(cv_path):
            send_tg_document(cv_path, "📎 CV для отклика")
    print("  [Kits] sent " + str(sent), flush=True)
    return sent


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


def extract_budget(text):
    """Pull a price/rate out of a title/description, e.g. '$700 / project'."""
    t = text or ""
    m = re.search(
        r'[€$£]\s?\d[\d,\.]*(?:k|K)?\s*(?:[–—-]|to)\s*[€$£]?\s?\d[\d,\.]*(?:k|K)?\s*(?:/|per\s+)\s*\w+',
        t,
    )
    if m:
        return m.group(0).strip()
    m = re.search(
        r'[€$£]\s?\d[\d,\.]*(?:k|K)?\s*(?:/|per\s+)\s*\w+',
        t,
    )
    if m:
        return m.group(0).strip()
    return ""


def _req_text(item):
    """Requirements arrive as {text, status, evidence} dicts (older rows: str)."""
    if isinstance(item, dict):
        return str(item.get("text", "") or "").strip()
    return str(item or "").strip()


def leads_to_tg(leads, send_fn=None, with_actions=True):
    if not leads:
        return
    send_fn = send_fn or send_tg_message

    leads_sorted = sorted(leads, key=lambda l: l.get("score", 0), reverse=True)
    CHUNK = 5
    verdict_icon = {"fit": "✅ ПОДХОДИТ", "partial": "⚠️ ЧАСТИЧНО", "no": "❌ НЕТ"}
    for chunk_start in range(0, len(leads_sorted), CHUNK):
        chunk = leads_sorted[chunk_start:chunk_start + CHUNK]
        keyboard = []
        label = f"🔥 <b>Новые лиды</b> · {chunk_start + 1}–{chunk_start + len(chunk)} из {len(leads_sorted)}\n" + "─" * 25
        msg = label
        for j, l in enumerate(chunk):
            n = chunk_start + j + 1
            title = html.escape(l["title"][:90].replace("#", ""))
            source = html.escape(l.get("source", "?"))
            url = html.escape(l.get("url", ""))
            verdict = l.get("verdict", "")
            reqs = [html.escape(t) for t in (_req_text(r) for r in (l.get("requirements") or [])[:3]) if t]
            risk = html.escape((l.get("risk") or "").strip()[:120])
            budget = extract_budget((l.get("title") or "") + " " + (l.get("description") or ""))
            fit = l.get("fit")
            fit_txt = f" · 🎯 fit {fit}/100" if fit is not None else ""
            msg += f"\n\n<b>{n}. {title}</b>\n⭐ {l.get('score', 0)}/10{fit_txt} · {source}"
            if budget:
                msg += f"\n💰 {html.escape(budget)}"
            _gates = l.get("gates") or {}
            _bad = [k for k, v in _gates.items() if v == "fail"]
            _warn = [k for k, v in _gates.items() if v == "flag"]
            if _bad:
                msg += f"\n⛔ гейты: {', '.join(_bad)}"
            elif _warn:
                msg += f"\n⚠️ гейты: {', '.join(_warn)}"
            if verdict in verdict_icon:
                msg += f"\n{verdict_icon[verdict]}"
            if reqs:
                msg += "\nНужно: " + ", ".join(reqs)
            if risk:
                msg += f"\n⚠️ {risk}"
            msg += f"\n🔗 <a href=\"{url}\">открыть</a>"
            if with_actions and l.get("url"):
                token = stable_hash(l["url"])
                keyboard.append([
                    {"text": f"✅ Откликнулся {n}", "callback_data": f"outcome:replied:{token}"},
                    {"text": f"⏭ Пропустить {n}", "callback_data": f"outcome:skipped:{token}"},
                ])
        send_fn(msg[:3900], reply_markup={"inline_keyboard": keyboard} if keyboard else None)


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
    print("[DBG] parse_remotive...", flush=True)
    all_raw.extend(parse_remotive())
    print("[DBG] parse_workingnomads...", flush=True)
    all_raw.extend(parse_workingnomads())
    print("[DBG] parse_nodesk...", flush=True)
    all_raw.extend(parse_nodesk())
    print("[DBG] parse_himalayas...", flush=True)
    all_raw.extend(parse_himalayas())
    # Arbeitnow disabled: German onsite board, produced noise with zero relevant leads
    print("[DBG] parse_n8n_community_jobs...", flush=True)
    all_raw.extend(parse_n8n_community_jobs())
    print("[DBG] parse_n8ndevs...", flush=True)
    all_raw.extend(parse_n8ndevs())
    print("[DBG] parse_peopleperhour...", flush=True)
    all_raw.extend(parse_peopleperhour())
    print("[DBG] parse_remoteai...", flush=True)
    all_raw.extend(parse_remoteai())
    print("[DBG] parse_automationroles...", flush=True)
    all_raw.extend(parse_automationroles())
    print("[DBG] parse_jobicy...", flush=True)
    all_raw.extend(parse_jobicy())
    print("[DBG] parse_web3career...", flush=True)
    all_raw.extend(parse_web3career())
    print("[DBG] parse_jobsdb...", flush=True)
    all_raw.extend(parse_jobsdb())
    print("[DBG] parse_solana_getro...", flush=True)
    all_raw.extend(parse_solana_getro())
    print("[DBG] parse_dynamitejobs...", flush=True)
    all_raw.extend(parse_dynamitejobs())
    # eFinancialCareers disabled: public listing exposes onsite US roles only,
    # remote filter returns zero relevant leads

    print(f"[Raw] Total leads collected: {len(all_raw)}", flush=True)

    # Age filter: drop leads older than MAX_LEAD_AGE_DAYS (30) where a date is known
    before_age = len(all_raw)
    all_raw = [l for l in all_raw if lead_fresh(l)]
    dropped_age = before_age - len(all_raw)
    if dropped_age:
        print(f"[Age] Dropped {dropped_age} leads older than {MAX_LEAD_AGE_DAYS} days", flush=True)

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
        result["posted_at"] = lead.get("posted_at")
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

    top_leads = [l for l in high_scored if l.get("score", 0) >= 8]
    mid_leads = [l for l in high_scored if l.get("score", 0) < 8]
    if mid_leads:
        print(f"[Digest] {len(mid_leads)} leads (6-7.9) saved for daily digest", flush=True)
    if top_leads:
        print_console(top_leads)
        leads_to_tg(top_leads)
        send_application_kits(top_leads, conn=conn)
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
    parser.add_argument("--digest", action="store_true", help="Send compact digest of pending 6-7.9 leads")
    parser.add_argument("--llm-usage", type=int, nargs="?", const=7, default=None,
                        help="Print LLM calls and spend for the last N days (default 7)")
    args = parser.parse_args()

    if args.llm_usage:
        llm_usage_report(args.llm_usage)
        return

    if args.digest:
        conn = init_db()
        send_daily_digest(conn)
        conn.close()
        return

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
