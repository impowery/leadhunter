# Converge 004

Статус: сделано и проверено на VPS.

- Цепочки (VPS): bulk → deepseek-v4.1-flash:free; quality → claude-haiku-5.5; escalate → deepseek-v4.1-flash-1017.
- Тестовый скоринг (`/tmp/bench_models.py deepseek-v4.1-flash:free`): оценки 9.5 / 8.5 / 0.0 (третья вакансия — мусор, ожидаемо без оценки), ok=True.
- Деплой: бэкап `lead_hunter_pro.py.bak.20261102-160111`, py_compile локально и на VPS, `start_bot.sh`, один процесс жив, трейсбеков в логе нет.
