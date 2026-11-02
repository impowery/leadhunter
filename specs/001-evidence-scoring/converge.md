# Converge

## Сделано
- Промпт: requirements (status + цитата), gates, dimensions; модель больше не ставит score.
- Валидация цитат: фраза, которой нет в описании, помечается uncited и даёт clarify.
- fit = 0.30*direction + 0.25*capability + 0.15*scope + 0.30*preferences; band и decision.
- score остаётся 0-10 (fit/10) для совместимости, verdict выводится из decision.
- Колонки fit, gates, evidence; сохранение в store_leads.
- Сообщение в Telegram: fit/100 и проваленные или спорные гейты.
- JSON-режим (response_format) и запрет прозы в ответе.
- Проверки: три кейса (79 / 98 / 0), uncited-тест, gate-fail-тест, смоук на VPS, бот перезапущен.

## Открыто
- Pairwise-ранжирование топа для дайджеста.
- Стадии откликов: interview, offer, rejected.
- Тонкая зарплатная логика: валюты и периоды.

## Замечания
- Лиды с keyword score < 2 не идут в LLM и остаются без fit.
