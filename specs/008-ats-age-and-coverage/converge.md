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

## JobStreet/SEEK SEA (26.11, второй проход)

Пользователь попросил азиатские борды, только топовые. Проверены живьём:

| борд | результат |
|---|---|
| JobStreet / SEEK (SG, MY, PH, ID) | **API `api/jobsearch/v5/search`, JSON без ключа — используется** |
| JobStreet / JobsDB **Thailand** | Cloudflare 403 (как прежний `parse_jobsdb`) |
| MyCareersFuture (SG gov) | API отдаёт JSON, но вакансии только сингапурские |
| Glints | 401/404, нужен приватный ключ |
| NodeFlair | 403 |
| Kalibrr, Foundit, Hiredly, Tech in Asia, JobBKK, JobTopgun | HTML-скрейпинг или мёртвый эндпоинт |
| SEEK AU-вариант, Wantedly (JP) | JSON, но вне профиля (Япония, японский язык) |

Реализован `parse_seek_asia()`. Конфиг в `sources.json` → `seek_asia` (сайты, ключевые
слова, `max_per_site`), правится без кода. Берутся только вакансии с
`workArrangements.id == 3` (Remote); 1 = On-site, 2 = Hybrid.

Важно: города в выдаче — это локация работодателя, а не ограничение работы. Гео-фильтр
по названию города отбрасывал 100% выдачи, поэтому для Remote-вакансий он не применяется:
релевантность плюс LLM-скоринг отсеивают остальное.

### Результат боевого прогона (07:43 UTC)
```
MY: 2   PH: 8   ID: 2   → 12 лидов
51763  AML Transaction Monitoring Analyst (HK Blockchain)   JobStreet PH  score 7.7  sent=1
51765  Finance and Settlements Support Assistant (AU)       JobStreet PH  score 7.3  sent=1
51771  Settlement Executive (Mandarin Speaker Only)         JobStreet ID  score 6.5  sent=1
51768  Senior Analyst, Treasury | WFH                       JobStreet PH  score 6.1  sent=-1 (в очереди)
51770  Compliance Analyst/KYC Officer - FinTech             JobStreet ID  score 5.8
51766  AU Mortgage Compliance Officer | Perm WFH            JobStreet PH  score 1.0  (отсеян)
```

Три отправленных лида — больше, чем дали все 16 новых ATS-бордов вместе.

Оговорка: `Settlement Executive` в выдаче помечен «Mandarin Speaker Only». Скоринг дал 6.5,
но требование языка стоит проверить вручную перед откликом.

## Языковой фильтр (26.11)

«Такие вакансии не нужны» — вакансии с требованием другого языка отсекаются до скоринга.

`language_blocked(lead)` смотрит заголовок **и** описание (у SEEK-лидов описание часто
пустое, требование стоит в заголовке). Блокируют только жёсткие формулировки рядом с языком:
speaker, speaking, fluent, fluency, required, mandatory, essential, only, proficiency, native.
Мягкие упоминания («Mandarin is a plus», «nice to have», «advantage») пропускаются.

Языки: mandarin, cantonese, japanese, korean, bahasa, vietnamese, thai, indonesian, tagalog,
turkish, arabic, spanish, portuguese, french, german, dutch, polish, italian.
Английский и русский — рабочие, не блокируются. `\bthai\b` не цепляет «Thailand».

Проверка на 9 кейсах — все верны:
```
blocked  Settlement Executive (Mandarin Speaker Only)
pass     AML Transaction Monitoring Analyst (HK Blockchain)
pass     Senior Analyst, Treasury | WFH
pass     "Knowledge of Mandarin is a plus."
blocked  Japanese-speaking Client Support
pass     "Thailand office in Bangkok. Fluent in English required."
blocked  "Cantonese required for Hong Kong coverage."
blocked  "Must speak Korean to cover Seoul counterparties."
pass     "Thai baht settlement experience."
```

Боевой прогон 08:17 UTC: `[Lang] Dropped 3 leads requiring another language`.
Прогон по 85 последним лидам в базе: 2 блокировки, обе настоящие —
`Settlement Executive (Mandarin Speaker Only)` и n8n-вакансия с
«Professional French skills are mandatory».

Замечание: лид `51771` (Mandarin) уже был отправлен до появления фильтра, откатить нельзя.
