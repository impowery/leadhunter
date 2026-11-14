#!/bin/bash
# LeadHunter watchdog: keep the scanner alive without manual restarts.
# Runs from cron every 10 minutes. Touches nothing outside /root/LeadHunter.
cd /root/LeadHunter || exit 1
LOG=leadhunter.log
STALE_MIN=420   # 7 hours: a normal cycle is a scan plus a 4 hour sleep

log() { echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) $*" >> watchdog.log; }

if ! pgrep -f "lead_hunter_pro.py --loop" >/dev/null; then
    log "not running -> starting"
    bash start_bot.sh >> watchdog.log 2>&1
    exit 0
fi

PID=$(pgrep -f "lead_hunter_pro.py --loop" | head -1)
if [ -n "$PID" ] && [ -n "$(find lead_hunter_pro.py sources.json -newer /proc/$PID 2>/dev/null)" ]; then
    log "code newer than running process -> restarting"
    bash start_bot.sh >> watchdog.log 2>&1
    exit 0
fi

if [ -f "$LOG" ] && [ -n "$(find "$LOG" -mmin +$STALE_MIN 2>/dev/null)" ]; then
    log "log stale for more than ${STALE_MIN} min -> restarting"
    bash start_bot.sh >> watchdog.log 2>&1
fi
