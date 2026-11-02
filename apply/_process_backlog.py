import json
import sqlite3
import time

import lead_hunter_pro as h

SINCE = "2026-10-25"
MAX_LLM = 400

conn = h.init_db()
rows = conn.execute(
    "SELECT id, title, description, url, source FROM leads "
    "WHERE created_at >= ? AND (score < 6 OR fit >= 60) ORDER BY id DESC",
    (SINCE,),
).fetchall()
print("candidates:", len(rows), flush=True)

scored, done, recommend, clarify = [], 0, 0, 0
for lid, title, desc, url, source in rows:
    if done >= MAX_LLM:
        break
    text = (title or "") + " " + (desc or "")
    if h.keyword_score(text).get("score", 0) < 2:
        continue
    try:
        r = h.llm_score(title, desc or "")
    except Exception as e:
        print("ERR", str(e)[:70], flush=True)
        continue
    done += 1
    fit = r.get("fit")
    decision = r.get("decision") or ""
    conn.execute(
        "UPDATE leads SET score=?, fit=?, reason=?, gates=?, evidence=?, matched_aspects=? WHERE id=?",
        (
            r.get("score", 0),
            fit,
            r.get("reason", ""),
            json.dumps(r.get("gates") or {}),
            json.dumps(r.get("requirements") or []),
            json.dumps(r.get("matched_aspects") or []),
            lid,
        ),
    )
    if decision == "recommend":
        recommend += 1
    elif decision == "clarify":
        clarify += 1
    if fit is not None and fit >= 60:
        scored.append({
            "title": title,
            "url": url,
            "source": source,
            "description": desc or "",
            "fit": fit,
            "decision": decision,
            "requirements": r.get("requirements") or [],
        })
        print("  %s | %s | %s" % (fit, decision, (title or "")[:55]), flush=True)
    if done % 25 == 0:
        conn.commit()
        print("scored:", done, "hits:", len(scored), flush=True)
    time.sleep(0.15)

conn.commit()
scored.sort(key=lambda x: x.get("fit") or 0, reverse=True)
print("DONE scored=%d recommend=%d clarify=%d strong=%d" % (done, recommend, clarify, len(scored)), flush=True)

for lead in scored:
    conn.execute("UPDATE leads SET sent=1 WHERE url=?", (lead["url"],))
conn.commit()

sent = h.send_application_kits(scored, limit=5, conn=conn)
print("kits sent:", sent, flush=True)

lines = ["📊 <b>Отчёт по лидам · 25.10–01.11</b>", "─" * 25,
         "Проверено LLM: %d · рекомендую: %d · частично: %d" % (done, recommend, clarify)]
if scored:
    lines.append("")
    lines.append("<b>Топ по fit:</b>")
    for i, lead in enumerate(scored[:8], 1):
        lines.append("%d. fit %s · %s · %s" % (
            i, lead["fit"], h.html.escape(lead.get("source") or "?"),
            h.html.escape((lead.get("title") or "")[:60])))
if sent:
    lines.append("")
    lines.append("📦 Пакеты отклика (письмо + ответы) отправлены выше, CV приложен файлом.")
h.send_owner_message("\n".join(lines)[:3900])
print("report sent", flush=True)
conn.close()
