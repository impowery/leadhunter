import sqlite3

conn = sqlite3.connect("/root/LeadHunter/leads.db")
rows = conn.execute(
    "SELECT title, url FROM leads WHERE source='eFinancialCareers' ORDER BY id DESC LIMIT 12"
).fetchall()
for title, url in rows:
    print(str(title)[:60], "|", url)
print()
tot = conn.execute("SELECT COUNT(*) FROM leads WHERE source='eFinancialCareers'").fetchone()[0]
rem = conn.execute(
    "SELECT COUNT(*) FROM leads WHERE source='eFinancialCareers' "
    "AND (lower(title) LIKE '%remote%' OR lower(url) LIKE '%remote%')"
).fetchone()[0]
print("total:", tot, "| with remote in title/url:", rem)
conn.close()
