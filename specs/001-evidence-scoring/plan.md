# План

1. lead_hunter_pro.py: новый промпт со структурой (requirements, gates, dimensions).
2. llm_score: валидация цитат, расчёт fit, band, decision, маппинг в score/verdict.
3. Миграция leads: колонки fit REAL, gates TEXT, evidence TEXT.
4. leads_to_tg: показать fit/100 и гейты.
5. Проверки: py_compile, локальный прогон llm_score на трёх кейсах.
6. Деплой на VPS, перезапуск, смоук на реальных лидах.
