import sqlite3

import lead_hunter_pro as h

conn = sqlite3.connect("/root/LeadHunter/leads.db")
rows = conn.execute(
    "SELECT source, COUNT(*), "
    "SUM(CASE WHEN fit >= 60 THEN 1 ELSE 0 END), "
    "SUM(CASE WHEN score >= 6 THEN 1 ELSE 0 END) "
    "FROM leads WHERE created_at >= datetime('now','-7 days') "
    "GROUP BY source ORDER BY COUNT(*) DESC"
).fetchall()

lines = [
    "\U0001F4CA <b>\u0418\u0441\u0442\u043e\u0447\u043d\u0438\u043a\u0438 \u0437\u0430 7 \u0434\u043d\u0435\u0439</b>",
    "\u2500" * 25,
    "\u0438\u0441\u0442\u043e\u0447\u043d\u0438\u043a \u00b7 \u043b\u0438\u0434\u043e\u0432 \u00b7 fit 60+ \u00b7 score 6+",
]
total = 0
fits = 0
for src, count, fit_count, good in rows:
    total += count
    fits += fit_count or 0
    lines.append("%s \u00b7 %d \u00b7 %d \u00b7 %d" % (
        h.html.escape(src or "?"), count, fit_count or 0, good or 0))
lines.append("")
lines.append("\u0418\u0442\u043e\u0433\u043e: %d \u043b\u0438\u0434\u043e\u0432 \u00b7 %d \u0441 fit 60+" % (total, fits))
lines.append("\u041d\u0443\u043b\u0435\u0432\u044b\u0435 \u0438\u0441\u0442\u043e\u0447\u043d\u0438\u043a\u0438 \u0441\u0442\u043e\u0438\u0442 \u043e\u0442\u043a\u043b\u044e\u0447\u0430\u0442\u044c.")
h.send_owner_message("\n".join(lines)[:3900])
conn.close()
print("source report sent")
