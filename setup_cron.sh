#!/bin/bash
TMP=$(mktemp)
crontab -l 2>/dev/null > "$TMP"
grep -q 'source_report.py' "$TMP" || echo '0 3 * * 1 cd /root/LeadHunter && ./venv/bin/python source_report.py >> source_report.log 2>&1' >> "$TMP"
crontab "$TMP"
rm -f "$TMP"
echo "--- cron ---"
crontab -l | tail -4
