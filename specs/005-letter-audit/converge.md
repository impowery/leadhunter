# Converge 005

Статус: закоммичено локально (13fd736), НЕ запушено, НЕ задеплоено, НЕ проверено на 3 вакансиях.

Сделано:
- Откатаны Supabase-правки (_SB_STATE, алерт, отключение _sb): решение владельца, вариант 2.
- Миграция kits.audit, audit_kit, audit в пакете отправлены в коммит 13fd736.
- Строка audit перенесена из leads_to_tg (там был kit вне области и сломанный отступ) в пакет send_application_kits.
- py_compile рабочей копии: OK.
- apply/_check_sb_path.py удалён (разрешено владельцем).

Осталось:
- Проверка audit_kit на 3 эталонных вакансиях.
- Деплой по AGENTS.md (бэкап, py_compile, scp, py_compile, start_bot.sh, процесс и лог).
- git push origin main после деплоя.
