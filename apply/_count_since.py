import sqlite3

conn = sqlite3.connect("/root/LeadHunter/leads.db")
rows = conn.execute(
    "SELECT substr(created_at,1,10) d, COUNT(*), SUM(score >= 6), SUM(sent=1) "
    "FROM leads WHERE created_at >= '2026-10-25' GROUP BY d ORDER BY d"
).fetchall()
print("date | total | score>=6 | sent")
for d, total, good, sent in rows:
    print(d, "|", total, "|", good, "|", sent)
print()
q = conn.execute(
    "SELECT COUNT(*) FROM leads WHERE created_at >= '2026-10-25' AND score < 6"
).fetchone()[0]
print("unscored (<6) since 25 Oct:", q)
conn.close()
