# Задачи 005

- [x] T0 Код audit_kit есть в рабочей копии (не в HEAD) — подтверждено чтением
- [ ] T1 py_compile рабочей копии lead_hunter_pro.py — ПАДАЕТ: IndentationError, строка ~3183. Блок audit-строки (`if kit.get("audit_problems")`) вставлен внутрь `if with_actions and l.get("url"):`. HEAD компилируется. Прод не затронут (работает на версии из f0134d1).
- [ ] T2 Решение владельца: что делать с Supabase-правками в той же правке (закоммитить отдельно / откатить / оставить)
- [ ] T3 Отделить audit-часть в отдельный коммит
- [ ] T4 Проверка audit_kit на 3 эталонных вакансиях
- [ ] T5 Бэкап на VPS, scp, py_compile на VPS, start_bot.sh, проверка процесса и лога
- [ ] T6 Коммит «letter audit pass (spec 005)» и push origin main
- [ ] T7 Не запускать apply/_check_sb_path.py без явного решения (пишет в прод-Supabase)
