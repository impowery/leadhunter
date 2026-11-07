# План 005

1. Разобрать незакоммиченную правку: audit (относится к 005) отделить от Supabase-правок (`_SB_STATE`, probe-скрипт). Решение владельца, см. spec.
2. Коммит только audit-части: `audit_kit`, `AUDIT_SYSTEM`, вызов в `build_application_kit`, столбец `kits.audit`, строка в TG.
3. Проверка на 3 эталонных вакансиях: вызвать `audit_kit` напрямую на локальном и VPS-окружении (без отправки в TG).
4. Деплой по AGENTS.md: бэкап на VPS → py_compile локально → scp → py_compile на VPS → `start_bot.sh` → процесс жив, без Traceback.
5. Коммит и push `origin main`.
