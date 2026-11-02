import time

import lead_hunter_pro as h

cases = [
    ("Trading Operations Associate",
     "Execute crypto trades, daily settlement and reconciliation, risk parameters, market neutral. Remote."),
    ("n8n Automation Engineer",
     "Build n8n workflows, AI agents, API integrations and Telegram bots. Remote, freelance."),
]
for title, desc in cases:
    start = time.time()
    r = h.llm_score(title, desc)
    took = time.time() - start
    print("%-38s fit=%-4s %-9s %.1fs" % (title[:38], r.get("fit"), r.get("decision"), took))
