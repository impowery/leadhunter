# Tasks 007

- [x] 1. `sources.json`: реестр ATS-бордов, disabled_sources, prefilter
- [x] 2. `_load_sources()` + `_enabled_boards()` с fallback на встроенные списки
- [x] 3. `GREENHOUSE_BOARDS` / `LEVER_BOARDS` из реестра (13 + 3)
- [x] 4. `ASHBY_BOARDS` + `parse_ashby_boards()` (новый ATS)
- [x] 5. `_maybe()` — пропуск выключенных источников по реестру
- [x] 6. Фильтр Telegram-каналов по `disabled_sources` (9 каналов выключено)
- [x] 7. `passes_prefilter()` — гейт до LLM
- [x] 8. Настройка порога по реальным данным (1546 лидов / 35 полезных)
- [x] 9. Проверка: py_compile локально и на VPS
- [x] 10. Проверка: живой Ashby (15 вакансий с paxos/bitvavo/keyrock)
- [x] 11. Проверка: префильтр на недельной базе (keep 19%, потеря полезных 0)
- [ ] 12. Деплой на VPS (ждёт решения: меняется поведение сканера)
- [ ] 13. Первый прогон после деплоя + сверка отчёта источников через неделю
