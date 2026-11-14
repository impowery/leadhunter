# CV evidence: what the resumes claim and what backs it

Purpose: keep the resumes honest and consistent. Before adding or changing a claim in
any CV, check here. Every line below was verified (server, API, logs or the owner),
with the date. If a fact is not here, verify it before writing it.

Last verified: 2026-11-14.

## Where the CVs live

| Lane | File used by the pipeline | Purpose |
|---|---|---|
| general | `C:/Users/Андрей/Desktop/Мои резюме/CV.pdf` (owner edits this) | default for anything unmatched |
| trading_ops | `resume/Andrey_Mashkin_Trading_Operations.pdf` | trading operations, middle office, reconciliation |
| crypto_ops | `resume/Andrey_Mashkin_Crypto_Operations.pdf` | crypto operations, compliance, due diligence, onboarding |
| ai | `resume/Andrey_Mashkin_AI_Automation.pdf` | LLM pipelines, n8n, MCP, RAG, automation contracts |
| payments | `resume/Andrey_Mashkin_Crypto_Payments.pdf` | stablecoin settlement, payments ops |

`apply/autofill.py` → `pick_cv()` chooses the lane from the job title and URL.
Source markdown for the four generated lanes lives beside the generator script; the PDFs
are produced by `md2pdf.py` (markdown → styled HTML → headless Chrome).
Owner: **Bangkok, Thailand (UTC+7)**, so onsite or hybrid roles in Bangkok are a fit,
not a blocker. This is encoded in `sources.json` → `eligibility.home_terms`.

## n8n (verified 2026-11-14)

Self-hosted on the VPS, in Docker Compose with its own PostgreSQL 16 and Redis.
Container `n8n-n8n-1`, uptime 4 weeks at the time of checking. 21 workflows in the
database, **5 active**. Executions recorded: 28 success, 22 error.

| Workflow | What it does | Runs per week |
|---|---|---|
| YouTube Upload Pipeline (Fixed) | `POST /webhook/youtube-upload`, secret check, upload to YouTube and TikTok via local servers, Telegram report | on demand |
| Crypto Watch | schedule, market data request, Telegram alert | 21 |
| Дайджест новостей | schedule, news, two HTTP requests | 14 |
| Breaking News Monitor | schedule, news monitoring | 7 |
| Market Movers | schedule, two HTTP requests | 7 |

Internal structure of the upload pipeline (verified from the workflow JSON):
`webhook → IF (Check Secret) → respondToWebhook 401 / respondToWebhook OK`,
then `httpRequest (YouTube)` and `httpRequest (TikTok)` into `merge → telegram`.

**Scope limit, do not overclaim:** n8n powers the MarketPrism content circuit only.
Pay, AutoTube and Films do not use it. Never write or imply that n8n orchestrates the
payments or trading stack.

CV wording in use (AI lane): "Run a self-hosted n8n instance (Docker, Postgres, Redis)
for content and market monitoring: webhook intake with secret validation and 401 handling,
IF branching, multi-platform publish with merge, Telegram reporting; scheduled news digests
and price alerts, about 49 runs a week." Other lanes mention `n8n workflow automation` in
the tooling block only.

## Other claims in the CVs and their evidence

- **10 venues** in daily reconciliation: CEX, DEX and on-chain, from the owner's own count.
- **99.96%+ uptime, 2 downtime incidents, ~24 minutes cumulative**: systemd journal for
  29 Oct - 14 Nov; the journal only keeps about two weeks, so the CV says
  "over the measured window" on purpose.
- **10 weeks without a reboot**, **zero failed units**, **100+ alerts a month**:
  owner's operational records.
- **8 production incidents, each closed with a root-cause fix**: owner's incident log.
- **15 hours a week removed by automation**: owner's estimate.
- **15 years in capital markets, $11M AUM at Nordbrook, contracts up to $200M at AIE**:
  the owner's career history.
- **2026 18% return was removed from the CV** and must not be reinstated: it was a single
  year (2015), presented as weak by the owner himself.

## Rules

1. Numbers in a CV must be traceable to this file or freshly verified.
2. No em or en dashes in CV text (the generation pipeline is checked for them).
3. Keep every generated CV to one page.
4. Do not claim n8n, RAG or LangChain work that has no artifact behind it.
