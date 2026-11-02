import sqlite3

conn = sqlite3.connect("/root/LeadHunter/leads.db")
for src in ("Arbeitnow", "eFinancialCareers", "WorkingNomads", "NoDesk", "Remotive"):
    row = conn.execute(
        "SELECT MAX(created_at) FROM leads WHERE source = ?", (src,)
    ).fetchone()
    print(src, "last:", row[0])
conn.close()
