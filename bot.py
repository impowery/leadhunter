import re, os, json, urllib.request, urllib.parse, asyncio
from datetime import datetime, timedelta
from pathlib import Path
from openai import OpenAI
import yfinance as yf
from html import escape
from telegram import Update, LabeledPrice
from telegram.ext import Application, CommandHandler, MessageHandler, PreCheckoutQueryHandler, filters

DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(exist_ok=True)

PREDICTIONS_FILE = DATA_DIR / "predictions.json"
OWNER_CHAT_ID = int(os.getenv("OWNER_CHAT_ID", "0"))
USAGE_FILE = DATA_DIR / "usage.json"
FREE_DAILY_LIMIT = 3
FREE_PREDICT_LIMIT = 1
PREMIUM_USERS = set()
_premium_file = DATA_DIR / "premium_users.json"
if _premium_file.exists():
    try:
        PREMIUM_USERS.update(json.loads(_premium_file.read_text()))
    except: pass

def load_usage() -> dict:
    if USAGE_FILE.exists():
        try:
            return json.loads(USAGE_FILE.read_text())
        except (json.JSONDecodeError, ValueError):
            pass
    return {}

def save_usage(data: dict):
    USAGE_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False))

def is_premium(chat_id: int) -> bool:
    return chat_id in PREMIUM_USERS

def check_limit(chat_id: int, command: str) -> tuple:
    if chat_id == OWNER_CHAT_ID or is_premium(chat_id):
        return True, ""
    today = datetime.utcnow().strftime("%Y-%m-%d")
    usage = load_usage()
    if usage.get("date") != today:
        usage = {"date": today, "users": {}}
    user = usage["users"].setdefault(str(chat_id), {"commands": 0, "predict": 0})
    if command == "predict":
        if user["predict"] >= FREE_PREDICT_LIMIT:
            return False, (
                f"\U0001f52e Free /predict limit reached ({FREE_PREDICT_LIMIT}/day).\n\n"
                f"\U0001f48e Premium: unlimited /predict + early signals + /monetize\n"
                f"\U0001f449 /premium to upgrade"
            )
        user["predict"] += 1
    if user["commands"] >= FREE_DAILY_LIMIT:
        return False, (
            f"\u26a1 Free daily limit reached ({FREE_DAILY_LIMIT}/day).\n\n"
            f"\U0001f48e Premium: unlimited commands + early signals\n"
            f"\U0001f449 /premium to upgrade"
        )
    user["commands"] += 1
    save_usage(usage)
    return True, ""

def save_prediction(asset: str, price: float, forecast: str, direction: str):
    preds = []
    if PREDICTIONS_FILE.exists():
        preds = json.loads(PREDICTIONS_FILE.read_text())
    preds.append({
        "asset": asset,
        "price_at_forecast": price,
        "forecast_text": forecast,
        "direction": direction,
        "timestamp": datetime.utcnow().isoformat(),
        "checked": False,
        "result": None,
    })
    PREDICTIONS_FILE.write_text(json.dumps(preds, indent=2))

def get_unchecked_predictions():
    if not PREDICTIONS_FILE.exists():
        return []
    try:
        preds = json.loads(PREDICTIONS_FILE.read_text())
    except (json.JSONDecodeError, ValueError):
        return []
    cutoff = (datetime.utcnow() - timedelta(hours=24)).isoformat()
    return [(i, p) for i, p in enumerate(preds) if not p.get("checked") and p.get("timestamp", "") < cutoff]

def mark_checked(index: int, result: str):
    if not PREDICTIONS_FILE.exists():
        return
    try:
        preds = json.loads(PREDICTIONS_FILE.read_text())
    except (json.JSONDecodeError, ValueError):
        return
    if 0 <= index < len(preds):
        preds[index]["checked"] = True
        preds[index]["result"] = result
        preds[index]["checked_at"] = datetime.utcnow().isoformat()
        PREDICTIONS_FILE.write_text(json.dumps(preds, indent=2, ensure_ascii=False))

def get_price(ticker: str):
    try:
        t = yf.Ticker(ticker)
        info = t.fast_info
        price = round(info.last_price, 2) if info.last_price else None
        prev = round(info.previous_close, 2) if info.previous_close else None
        if price and prev:
            change = round((price - prev) / prev * 100, 2)
            return price, change
    except Exception as e:
        print(f"Price fetch error for {ticker}: {e}")
    return None, None



def fetch_url(url):
    """Читает веб-страницу через Jina Reader (бесплатно, без ключа)"""
    try:
        encoded = urllib.parse.quote(url, safe='')
        req = urllib.request.Request(
            f"https://r.jina.ai/{encoded}",
            headers={"User-Agent": "Mozilla/5.0", "Accept": "text/plain"}
        )
        with urllib.request.urlopen(req, timeout=15) as r:
            text = r.read().decode("utf-8", errors="replace")
            if len(text) > 8000:
                text = text[:8000] + "\n\n[...truncated]"
            return text
    except Exception as e:
        print(f"fetch_url error: {e}")
        return None

def clean_md(text):
    text = re.sub(r'\*{1,2}(.*?)\*{1,2}', r'<b>\1</b>', text)
    text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)
    return text.strip()

API_KEY = os.getenv("OPENROUTER_API_KEY") or os.getenv("GROQ_API_KEY")

client = OpenAI(
    api_key=API_KEY,
    base_url="https://openrouter.ai/api/v1"
)

FALLBACK_MODELS = [
    "deepseek/deepseek-chat",
    "google/gemini-2.0-flash-001",
    "meta-llama/llama-3.3-70b-instruct",
]

def ask_llm(messages, temperature=0.7, timeout=30):
    """Try models in order, skip on 429"""
    for model in FALLBACK_MODELS:
        try:
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                timeout=timeout,
            )
            return response.choices[0].message.content
        except Exception as e:
            print(f"Model {model} failed: {e}")
            continue
    return None

SYSTEM_PROMPT = (
    "You are a research analyst. The user asks a question or gives a topic. "
    "Provide a structured report:\n"
    "1. Executive Summary (2-3 sentences)\n"
    "2. Key Facts (3-5 points)\n"
    "3. Analysis & Conclusions\n"
    "4. Recommendations\n\n"
    "Be specific, no fluff. Write in English."
)

TICKER_MAP = {
    "btc": "BTC-USD",
    "bitcoin": "BTC-USD",
    "eth": "ETH-USD",
    "ethereum": "ETH-USD",
    "sp500": "^GSPC",
    "snp": "^GSPC",
    "oil": "CL=F",
    "wti": "CL=F",
    "crude": "CL=F",
    "gold": "GC=F",
    "xau": "GC=F",
}

PERSPECTIVES = {
    "\U0001f7e0 Optimist": "You are an optimistic analyst. Find the best scenarios and arguments for growth. Point out specific levels and catalysts.",
    "\U0001f535 Realist": "You are a pragmatic analyst. Assess the most likely course of events. Rely on data, not emotions.",
    "\U0001f534 Pessimist": "You are a critical analyst. Find the main risks and worst-case scenarios. Point out support levels and what could go wrong.",
    "\U0001f7e3 Expert": "You are a professional trader with 20 years of experience. Give deep technical and fundamental analysis. Mention key levels, volumes, patterns.",
}

MONETIZE_PROMPT = """You are a startup advisor and monetization strategist.

Analyze the given product and return a structured assessment:

1. PRODUCT TYPE: What is this? (bot, channel, SaaS, API, marketplace)
2. TARGET AUDIENCE: Who would pay? Be specific (not "everyone").
3. MARKET SIZE: Estimate TAM/SAM/SOM with numbers.
4. COMPETITORS: List 3-5 direct competitors with their pricing.
5. MONETIZATION STRATEGIES: 5 strategies from easiest to hardest.
   For each: setup time, monthly revenue potential, risk level (low/med/high).
6. VIRAL LOOP: How can users bring other users for free? Be specific, not generic.
7. PRICING: Suggest specific price points. Don't say "it depends".
8. GO/NO-GO: Verdict with confidence %. What to build first.

Format: structured, specific numbers, actionable. No fluff."""

PRODUCT_CONTEXT = {
    "content factory": "AI-powered Telegram channel that auto-posts market analysis 3x/day with real-time price data (BTC, ETH, S&P 500, Oil, Gold). Uses LLM to generate analysis + AI images. Has /generate for custom posts.",
    "predict bot": "Telegram bot with /predict (4-perspective market forecasts with synthesis) and /research (deep topic analysis). Uses yfinance for real-time data, OpenRouter LLM with fallback models.",
    "market channel": "Russian-language Telegram channel with AI-generated market analysis posts. Auto-posts 3x/day via cron. Content includes real prices, % changes, and expert-style commentary with AI images.",
}


MONETIZE_PROMPT = """You are a startup advisor and monetization strategist.

Analyze the given product and return a structured assessment:

1. PRODUCT TYPE: What is this? (bot, channel, SaaS, API, marketplace)
2. TARGET AUDIENCE: Who would pay? Be specific (not "everyone").
3. MARKET SIZE: Estimate TAM/SAM/SOM with numbers.
4. COMPETITORS: List 3-5 direct competitors with their pricing.
5. MONETIZATION STRATEGIES: 5 strategies from easiest to hardest.
   For each: setup time, monthly revenue potential, risk level (low/med/high).
6. VIRAL LOOP: How can users bring other users for free? Be specific, not generic.
7. PRICING: Suggest specific price points. Don't say "it depends".
8. GO/NO-GO: Verdict with confidence %. What to build first.

Format: structured, specific numbers, actionable. No fluff."""

PRODUCT_CONTEXT = {
    "content factory": "AI-powered Telegram channel that auto-posts market analysis 3x/day with real-time price data (BTC, ETH, S&P 500, Oil, Gold). Uses LLM to generate analysis + AI images. Has /generate for custom posts.",
    "predict bot": "Telegram bot with /predict (4-perspective market forecasts with synthesis) and /research (deep topic analysis). Uses yfinance for real-time data, OpenRouter LLM with fallback models.",
    "market channel": "Russian-language Telegram channel with AI-generated market analysis posts. Auto-posts 3x/day via cron. Content includes real prices, % changes, and expert-style commentary with AI images.",
}



async def run_verification():
    unchecked = get_unchecked_predictions()
    if not unchecked:
        print("No unchecked predictions found.")
        return

    print(f"Found {len(unchecked)} unchecked predictions.")

    TICKER_MAP_LOCAL = {
        "btc": "BTC-USD",
        "bitcoin": "BTC-USD",
        "eth": "ETH-USD",
        "ethereum": "ETH-USD",
        "sp500": "^GSPC",
        "snp": "^GSPC",
        "oil": "CL=F",
        "wti": "CL=F",
        "crude": "CL=F",
        "gold": "GC=F",
        "xau": "GC=F",
    }

    for idx, pred in unchecked:
        ticker = TICKER_MAP_LOCAL.get(pred.get("asset", "").lower(), pred.get("ticker", ""))
        direction = pred.get("direction", "sideways")
        old_price = pred.get("price_at_forecast", 0)
        asset = pred.get("asset", "?")

        current_price, _ = get_price(ticker)
        if not current_price:
            print(f"  {asset}: couldn't get current price, skipping")
            continue

        price_change_pct = (current_price - old_price) / old_price * 100 if old_price else 0

        if price_change_pct > 1.0:
            actual = "up"
        elif price_change_pct < -1.0:
            actual = "down"
        else:
            actual = "sideways"

        result = "correct" if direction == actual else "incorrect"
        mark_checked(idx, result)
        print(f"  {asset}: forecast={direction}, actual={actual} ({price_change_pct:+.2f}%), result={result}")


def search_web(topic):
    """Парсит Google News по теме через Jina Reader"""
    try:
        query = urllib.parse.quote(topic)
        url = f"https://r.jina.ai/https://news.google.com/search?q={query}&hl=en-US&gl=US&ceid=US:en"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as r:
            text = r.read().decode("utf-8", errors="replace")
            if text and len(text) > 200:
                return text[:6000]
    except Exception as e:
        print(f"search_web error: {e}")
    return None

async def research(update: Update, context):
    allowed, msg = check_limit(update.effective_chat.id, "research")
    if not allowed:
        await update.message.reply_text(msg)
        return

    query = update.message.text
    status = await update.message.reply_text("Researching...")

    news = search_web(query)
    context_msg = query
    if news:
        context_msg = f"User question: {query}\n\nRecent web content on this topic:\n{news}\n\nUse the web content to provide up-to-date information. If relevant, cite sources."

    result = ask_llm([
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": context_msg}
    ])

    if result:
        await status.edit_text(clean_md(result))
    else:
        await status.edit_text("Error: all models failed")

async def predict(update: Update, context):
    import sys
    print(f"PREDICT CALLED: chat={update.effective_chat.id} text={update.message.text}", flush=True)
    allowed, msg = check_limit(update.effective_chat.id, "predict")
    if not allowed:
        await update.message.reply_text(msg)
        return

    asset = update.message.text.replace("/predict", "").strip().lower()
    if not asset:
        await update.message.reply_text(
            "\U0001f52e Specify an asset after /predict\n\n"
            "Examples:\n"
            "/predict btc\n"
            "/predict eth\n"
            "/predict gold\n"
            "/predict oil\n"
            "/predict sp500"
        )
        return

    ticker = TICKER_MAP.get(asset)
    if not ticker:
        names = ", ".join(sorted(TICKER_MAP.keys()))
        await update.message.reply_text(f"\u274c Unknown asset: {asset}. Available: {names}")
        return

    status = await update.message.reply_text(f"\U0001f52e Analyzing {asset.upper()}...")

    try:
        t = yf.Ticker(ticker)
        info = t.fast_info
        price = round(info.last_price, 2) if info.last_price else None
        prev = round(info.previous_close, 2) if info.previous_close else None
    except Exception:
        price = prev = None

    if price and prev:
        change = round((price - prev) / prev * 100, 2)
        data_line = f"Current price: ${price:,.2f} ({change:+.2f}% 24h)"
    else:
        data_line = "Price data unavailable"

    results = []
    for name, prompt in PERSPECTIVES.items():
        try:
            text = ask_llm([
                {"role": "system", "content": prompt},
                {"role": "user", "content": f"Asset: {asset.upper()} ({ticker})\n{data_line}\n24h forecast. STRICTLY 2-3 sentences max. Be specific with numbers and levels."},
            ])
            results.append(f"{name}:\n{clean_md(text) if text else 'no response'}")
        except Exception as e:
            results.append(f"{name}: error")
            print(f"Perspective error: {e}")

    synthesis_prompt = (
        f"You are the chief analyst. You have 4 forecasts for {asset.upper()}.\n"
        f"{data_line}\n\n"
        f"Here are the forecasts:\n"
        f"{chr(10).join(results)}\n\n"
        f"Synthesize into a single conclusion:\n"
        f"1. Overall assessment (up/down/sideways) with probability in %\n"
        f"2. Key argument FOR and AGAINST\n"
        f"3. One specific recommendation: buy, sell, or wait\n\n"
        f"Keep it short, 4-6 sentences."
    )

    try:
        synth_raw = ask_llm([
            {"role": "system", "content": "You are the chief analyst. Answer briefly and specifically."},
            {"role": "user", "content": synthesis_prompt},
        ], temperature=0.5)
        synthesis = clean_md(synth_raw) if synth_raw else "Synthesis unavailable"
    except Exception:
        synthesis = "Synthesis unavailable"

    result = (
        f"<b>Forecast: {escape(asset.upper())}</b>\n"
        f"{data_line}\n\n"
        f"{'\n\n'.join(results)}\n\n"
        f"<b>SUMMARY:</b>\n{synthesis}"
    )

    # Determine direction from synthesis
    synth_lower = synthesis.lower() if synthesis else ""
    if any(w in synth_lower for w in ["up", "bullish", "growth", "rise", "rally"]):
        direction = "up"
    elif any(w in synth_lower for w in ["down", "bearish", "decline", "drop", "fall"]):
        direction = "down"
    else:
        direction = "sideways"

    # Save prediction
    if price:
        try:
            save_prediction(asset, price, synthesis, direction)
        except Exception as e:
            print(f"save_prediction failed: {e}", flush=True)

    await status.edit_text(result[:4096], parse_mode='HTML')

async def monetize(update: Update, context):
    allowed, msg = check_limit(update.effective_chat.id, "monetize")
    if not allowed:
        await update.message.reply_text(msg)
        return

    product = update.message.text.replace("/monetize", "").strip().lower()
    if not product:
        await update.message.reply_text(
            "\U0001f4b0 Describe your product after /monetize\n\n"
            "Quick options:\n"
            "/monetize content factory\n"
            "/monetize predict bot\n"
            "/monetize market channel\n\n"
            "Or describe any product:\n"
            "/monetize AI-powered fitness tracker app"
        )
        return

    status = await update.message.reply_text(f"\U0001f4b0 Analyzing monetization for: {product}...")

    context_hint = ""
    for key, desc in PRODUCT_CONTEXT.items():
        if key in product:
            context_hint = f"\n\nContext about this product: {desc}"
            break

    prompt = f"Product: {product}{context_hint}\n\nProvide full monetization analysis."

    result = ask_llm([
        {"role": "system", "content": MONETIZE_PROMPT},
        {"role": "user", "content": prompt},
    ], temperature=0.7)

    if result:
        await status.edit_text(clean_md(result)[:4096])
    else:
        await status.edit_text("\u274c All models failed. Try again later.")



async def accuracy(update: Update, context):
    if not PREDICTIONS_FILE.exists():
        await update.message.reply_text("\U0001f4ca \u041f\u0440\u043e\u0433\u043d\u043e\u0437\u043e\u0432 \u043f\u043e\u043a\u0430 \u043d\u0435\u0442. \u0418\u0441\u043f\u043e\u043b\u044c\u0437\u0443\u0439\u0442\u0435 /predict")
        return

    preds = json.loads(PREDICTIONS_FILE.read_text())
    checked = [p for p in preds if p["checked"]]

    if not checked:
        total = len(preds)
        await update.message.reply_text(
            f"\U0001f4ca \u041f\u0440\u043e\u0433\u043d\u043e\u0437\u043e\u0432 \u0441\u0434\u0435\u043b\u0430\u043d\u043e: {total}\n"
            f"\u23f3 \u041e\u0436\u0438\u0434\u0430\u044e\u0442 \u043f\u0440\u043e\u0432\u0435\u0440\u043a\u0438: {total}\n"
            f"\u2705 \u041f\u0440\u043e\u0432\u0435\u0440\u0435\u043d\u043e: 0\n\n"
            f"\u0420\u0435\u0437\u0443\u043b\u044c\u0442\u0430\u0442\u044b \u043f\u043e\u044f\u0432\u044f\u0442\u0441\u044f \u0447\u0435\u0440\u0435\u0437 24 \u0447\u0430\u0441\u0430"
        )
        return

    correct = sum(1 for p in checked if p["result"] == "correct")
    total = len(preds)
    pct = round(correct / len(checked) * 100, 1)

    by_asset = {}
    for p in checked:
        a = p["asset"].upper()
        if a not in by_asset:
            by_asset[a] = {"correct": 0, "total": 0}
        by_asset[a]["total"] += 1
        if p["result"] == "correct":
            by_asset[a]["correct"] += 1

    asset_lines = []
    for a, d in sorted(by_asset.items()):
        pct_a = round(d["correct"] / d["total"] * 100, 1)
        asset_lines.append(f"  {a}: {d['correct']}/{d['total']} ({pct_a}%)")

    await update.message.reply_text(
        f"\U0001f4ca Accuracy Report\n\n"
        f"\u2705 \u041f\u0440\u0430\u0432\u0438\u043b\u044c\u043d\u044b\u0445: {correct}/{len(checked)} ({pct}%)\n"
        f"\u23f3 \u041e\u0436\u0438\u0434\u0430\u044e\u0442 \u043f\u0440\u043e\u0432\u0435\u0440\u043a\u0438: {total - len(checked)}\n"
        f"\U0001f4dd \u0412\u0441\u0435\u0433\u043e \u043f\u0440\u043e\u0433\u043d\u043e\u0437\u043e\u0432: {total}\n\n"
        f"By asset:\n" + "\n".join(asset_lines)
    )


async def autopost(update: Update, context):
    channel_id = os.getenv("CHANNEL_YIELDTOP5")
    if not channel_id:
        await update.message.reply_text("\u274c CHANNEL_YIELDTOP5 not configured")
        return

    status_msg = await update.message.reply_text("\U0001f4e1 Generating forecast...")

    assets = [
        ("BTC", "BTC-USD", "bitcoin"),
        ("ETH", "ETH-USD", "ethereum"),
        ("S&P 500", "^GSPC", "S&P 500 index"),
        ("Oil", "CL=F", "crude oil"),
        ("Gold", "GC=F", "gold"),
    ]

    parts = []
    for name, ticker, display in assets:
        try:
            t = yf.Ticker(ticker)
            info = t.fast_info
            price = round(info.last_price, 2) if info.last_price else None
            prev = round(info.previous_close, 2) if info.previous_close else None
            if price and prev:
                change = round((price - prev) / prev * 100, 2)
                arrow = "▲" if change >= 0 else "▼"
                parts.append(f"<b>{name}</b> — ${price:,.2f} {arrow} {change:+.2f}%")
            elif price:
                parts.append(f"<b>{name}</b> — ${price:,.2f}")
        except:
            parts.append(f"<b>{name}</b> — N/A")

    market_data = "\n\n".join(parts)

    prompt = f"""CRITICAL RULES:
- Write ONLY in English. Never use Russian or any other language.
- End with: 📊 AI market forecasts with target levels → @my23agents_bot
- Do NOT say "crypto forecasts" — we cover ALL assets (crypto, stocks, oil, gold, indices)

Market data:
{market_data}

You are a financial analyst writing for YieldTop5 Telegram channel.

Write a structured market forecast post. STRICT FORMAT:

📈 <b>Market Watch</b>

<b>BTC/USD</b> — $65,000 ▲ +1.2%
Short-term forecast in 2-3 sentences. Key levels: support $X, resistance $Y. Probability: Z%.

<b>ETH/USD</b> — $1,750 ▼ -0.5%
Forecast in 2-3 sentences. Key levels: support $X, resistance $Y. Probability: Z%.

<b>S&P 500</b> — $7,400 ▼ -0.8%
Forecast in 2-3 sentences. Key levels: support $X, resistance $Y. Probability: Z%.

<b>Oil WTI</b> — $74 ▲ +0.3%
Forecast in 2-3 sentences. Key levels: support $X, resistance $Y. Probability: Z%.

<b>Gold</b> — $4,300 ▼ -0.5%
Forecast in 2-3 sentences. Key levels: support $X, resistance $Y. Probability: Z%.

Rules:
- Use HTML tags: <b>bold</b> for asset names
- Each asset gets its OWN paragraph with blank line before it
- Include current price and 24h change with arrows
- Give specific price levels (support/resistance)
- Give probability % for direction
- 2-3 sentences per asset, no fluff
"""

    response = ask_llm([
        {"role": "system", "content": "You are a financial analyst writing for YieldTop5 Telegram channel. Use HTML: <b>bold</b> for asset names. Each asset in its own paragraph with blank line."},
        {"role": "user", "content": prompt}
    ], temperature=0.7)

    forecast_text = clean_md(response) if response else "Forecast unavailable"

    message = f"\U0001f4c8 <b>Market Watch</b>\n\n{market_data}\n\n{forecast_text}"

    try:
        await context.bot.send_message(chat_id=channel_id, text=message, parse_mode="HTML")
        await status_msg.edit_text(f"\u2705 Posted to channel\n\n{message[:500]}...")
    except Exception as e:
        await status_msg.edit_text(f"\u274c Failed to post: {e}")




async def read_url_cmd(update: Update, context):
    """Читает URL и возвращает AI-саммари"""
    args = context.args
    if not args:
        await update.message.reply_text(
            "Usage: /read <url>\n\n"
            "Example: /read https://news.ycombinator.com"
        )
        return

    url = args[0]
    if not url.startswith("http"):
        url = "https://" + url

    status = await update.message.reply_text("Reading page...")
    content = fetch_url(url)

    if not content:
        await status.edit_text("Error: couldn't read the page. Try another URL.")
        return

    if len(content) < 200:
        await status.edit_text(f"Page too short or blocked:\n\n{content[:1000]}")
        return

    result = ask_llm([
        {"role": "system", "content": "You read web pages and summarize them. Respond with:\n1. What this page is about (1 sentence)\n2. Key points (3-5 bullet points)\n3. Your analysis or opinion\n\nBe concise."},
        {"role": "user", "content": f"Summarize this page content:\n\n{content}"}
    ])

    if result:
        await status.edit_text(clean_md(result)[:4000])
    else:
        await status.edit_text("Error summarizing page. Raw content:\n\n" + content[:2000])

async def premium_cmd(update: Update, context):
    chat_id = update.effective_chat.id
    if is_premium(chat_id):
        await update.message.reply_text("\u2705 You already have Premium! All limits removed.")
        return
    await context.bot.send_invoice(
        chat_id=chat_id,
        title="Premium Plan \u2014 Monthly",
        description="Unlimited /predict, /research, /monetize + early signals + /accuracy tracking",
        payload="premium_monthly",
        currency="XTR",
        prices=[LabeledPrice("Premium Monthly", PREMIUM_STARS)],
    )



async def precheckout(update: Update, context):
    query = update.pre_checkout_query
    if query.invoice_payload == "premium_monthly":
        await query.answer(ok=True)
    else:
        await query.answer(ok=False, error_message="Invalid payment")

async def successful_payment(update: Update, context):
    chat_id = update.effective_chat.id
    PREMIUM_USERS.add(chat_id)
    premium_file = DATA_DIR / "premium_users.json"
    users = []
    if premium_file.exists():
        try:
            users = json.loads(premium_file.read_text())
        except: pass
    if chat_id not in users:
        users.append(chat_id)
    premium_file.write_text(json.dumps(users))
    await update.message.reply_text(
        "\U0001f48e <b>Premium activated!</b>\n\n"
        "\u2705 Unlimited /predict (4 perspectives)\n"
        "\u2705 Unlimited /research and /monetize\n"
        "\u2705 Early signals before channel posts\n"
        "\u2705 Full /accuracy tracking\n\n"
        "Thank you! \U0001f680",
        parse_mode='HTML'
    )


async def start(update: Update, context):
    await update.message.reply_text(
        "\U0001f916 AI Research & Forecast Bot\n\n"
        "/predict <asset> — 4-perspective market forecast\n"
        "/accuracy — prediction accuracy statistics\n"
        "/autopost — generate and post forecast to channel\n"
        "/monetize <product> — monetization strategy analysis\n"
        "/research <topic> — deep research on any topic\n"
        "/read <url> — read and summarize any web page\n\n"
        "Assets: btc, eth, sp500, oil, gold"
    )

async def auto_market_update(app):
    """Каждые 6 часов присылает владельцу рынки + новости"""
    await asyncio.sleep(30)
    while True:
        try:
            if not OWNER_CHAT_ID:
                await asyncio.sleep(21600)
                continue

            assets = [
                ("BTC", "BTC-USD"), ("ETH", "ETH-USD"),
                ("S&P 500", "^GSPC"), ("Oil", "CL=F"), ("Gold", "GC=F"),
            ]
            price_lines = []
            for name, ticker in assets:
                try:
                    t = yf.Ticker(ticker)
                    info = t.fast_info
                    price = round(info.last_price, 2) if info.last_price else None
                    prev = round(info.previous_close, 2) if info.previous_close else None
                    if price and prev:
                        change = round((price - prev) / prev * 100, 2)
                        arrow = "\u25b2" if change >= 0 else "\u25bc"
                        price_lines.append(f"<b>{name}</b> \u2014 ${price:,.2f} {arrow} {change:+.2f}%")
                except:
                    price_lines.append(f"<b>{name}</b> \u2014 N/A")

            market_text = "\n".join(price_lines)

            news = search_web("stock market today")
            news_section = ""
            if news:
                result = ask_llm([
                    {"role": "system", "content": "Summarize the latest market news in 3-5 bullet points. Be concise."},
                    {"role": "user", "content": f"Market news:\n{news[:4000]}"}
                ])
                if result:
                    news_section = f"\n\n\U0001f4f0 <b>Market News</b>\n{clean_md(result)}"

            message = f"\U0001f4c8 <b>Market Update</b>\n\n{market_text}{news_section}\n\n\U0001f916 AI-powered by @my23agents_bot"
            await app.bot.send_message(chat_id=OWNER_CHAT_ID, text=message[:4000], parse_mode="HTML")
            print(f"Auto update sent to {OWNER_CHAT_ID}", flush=True)
        except Exception as e:
            print(f"auto_market_update error: {e}", flush=True)

if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.DEBUG, format="%(asctime)s %(levelname)s: %(message)s")
    print("BOT STARTING", flush=True)
    app = Application.builder().token(os.getenv("TG_BOT_TOKEN")).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("predict", predict))
    app.add_handler(CommandHandler("monetize", monetize))
    app.add_handler(CommandHandler("accuracy", accuracy))
    app.add_handler(CommandHandler("autopost", autopost))
    app.add_handler(CommandHandler("read", read_url_cmd))
    app.add_handler(CommandHandler("premium", premium_cmd))
    app.add_handler(PreCheckoutQueryHandler(precheckout))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, research))

    async def startup():
        asyncio.create_task(auto_market_update(app))

    app.post_init = startup
    app.run_polling()

