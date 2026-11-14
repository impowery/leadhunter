@echo off
chcp 65001 >nul
title LeadHunter status
echo ==========================================
echo  LeadHunter status (read only)
echo ==========================================
echo.
ssh -i "C:\Users\Андрей\.ssh\vps_opencode" -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null root@193.233.19.171 "cd /root/LeadHunter && echo PROCESS: && (ps -eo pid,etime,args | grep '[l]ead_hunter_pro' || echo 'NOT RUNNING') && echo && echo LAST LOG: && tail -5 leadhunter.log && echo && echo ERRORS IN LAST 300 LINES: && tail -300 leadhunter.log | grep -ciE 'traceback|\[warn\]' && echo && echo LAST SCAN: && grep -E 'Total leads collected|Sleeping' leadhunter.log | tail -2"
echo.
pause
