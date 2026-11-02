import sqlite3
import sys

if len(sys.argv) < 2:
    sys.exit(0)
conn = sqlite3.connect("/root/LeadHunter/leads.db")
row = conn.execute("SELECT letter FROM kits WHERE url = ?", (sys.argv[1],)).fetchone()
if row and row[0]:
    sys.stdout.write(row[0])
conn.close()
