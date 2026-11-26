# 008 — сходимость

Проверено на живом прогоне 26.11, 07:19 UTC, VPS.

## Метки ATS
`parse_greenhouse_boards()` локально: 7 лидов, у всех `from_ats=True`.
`lead_fresh(APAC 57 дней, from_ats)` → `True`; `(RSS 57 дней)` → `False`;
`(ATS + «no longer accepting applications»)` → `False`.

## Реестр
greenhouse 30 записей (29 включённых, `kraken` — disabled, слаг не найден),
lever 6, ashby 5. JSON валиден, `py_compile` чист на обеих машинах.

Добавлено: gh — primexbt, ebanx, billcom, gocardless, wise, monzo, mercury, sumup,
brex, woo, luno, blockchain, ripple; lv — certik, anchorage, moonpay.
При проверке отброшены живые, но нецелевые/onsite-борды: ripple (109 вакансий, 0 remote),
fireblocks (37, 0 remote), blockchain (38, 0 remote), bitwarden (password manager).

## Результат прогона после правки
```
51753  Crypto Operations Associate - APAC      Greenhouse alpaca     score 8.0  fit 80  sent=1
51754  Trading Operations Specialist           Greenhouse primexbt   score 7.5  fit 75  sent=1
```
APAC — та самая вакансия, потерянная по возрасту. primexbt — новый борд, дал
отправляемую вакансию в первом же цикле.

## Наблюдение
Из 16 живых новых бордов сейчас только 2 отдают ops+remote. Это структурно: ATS-вакансии
в основном onsite или geo-locked. Расширение работает на накопление, не на мгновенный
скачок. Третья причина обвала (исчерпание старых job-бордов и дедуп) этой спекой
не закрыта.

## Побочно вошло в коммит
Незакоммиченные правки прошлой сессии, уже бывшие в проде: логирование отклонённых
TG-сообщений (`send_tg_message`), фикс голых HTML-entities в `parse_nodesk`.
