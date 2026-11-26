# 008 — задачи

- [x] `from_ats: True` в greenhouse-парсере
- [x] `from_ats: True` в lever-парсере
- [x] `from_ats: True` в ashby-парсере
- [x] `lead_fresh()`: ранний True для ATS после CLOSED_PATTERNS
- [x] Изолированный тест lead_fresh: APAC 57д → True, RSS 57д → False, ATS-closed → False
- [x] Проба ~150 слагов по трём API, отбор профильных
- [x] `sources.json`: +13 greenhouse, +3 lever (итого 30 / 6 / 5)
- [x] py_compile локально и на VPS
- [x] Деплой: бэкап, scp, рестарт через start_bot.sh
- [x] Смоук: прогон до Greenhouse, APAC и primexbt в базе
