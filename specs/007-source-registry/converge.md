# Converge 007

Статус: код готов и проверен локально, закоммичен. НЕ задеплоен: меняется поведение
сканера, нужен отдельный прогон и подтверждение владельца.

## Что сделано

- `sources.json` — реестр: 13 Greenhouse + 3 Lever + 4 Ashby включены, 18 источников
  и каналов выключены, prefilter включён.
- `lead_hunter_pro.py`:
  - `_load_sources()` / `_enabled_boards()`: списки бордов берутся из JSON, при ошибке —
    встроенный fallback.
  - `parse_ashby_boards()` — новый ATS (paxos, bitvavo, keyrock, prelude).
  - `_maybe(label, fn)` — выключенный источник не вызывается, в лог пишется `[Skip]`.
  - Telegram-каналы фильтруются на старте: было 12+, осталось 5.
  - `passes_prefilter()` применяется к `all_raw` после фильтра по возрасту и до скоринга,
    с логом `[Prefilter] Dropped N of M` и разбивкой по источникам.

## Проверено

1. `py_compile` локально и на VPS — OK.
2. Живой Ashby: 15 вакансий (paxos 7, bitvavo 3, keyrock 5), парсер возвращает лиды
   в общем формате (`title`, `url`, `source`, `description`, `posted_at`).
3. Префильтр на реальной базе за 7 дней: 1546 лидов → 300 (19%), из 35 известных
   полезных не потеряно ни одного.
   Отсечено: Jobicy 608, Telegram @jobstash 199, WeWorkRemotely 151,
   AutomationRoles 94, Reddit 43, Solana 25.
4. Реестр: 13 Greenhouse, 3 Lever, 4 Ashby, 5 Telegram-каналов, 18 выключенных записей.

## Почему порог именно такой

Первая версия считала попадания по широкому словарю описания — её проходило 100% лидов,
то есть гейт не работал. Вторая (заголовок ИЛИ 3 слова в теле) отсекала 86%, но теряла
3 полезных лида. Итоговая: заголовок по расширенному списку ИЛИ узкие фразы в теле
(reconciliation, trade lifecycle, break investigation, middle office, post-trade,
settlement, trade support, asset servicing). Отсекает 81%, потерь ноль.

## Осталось

- Деплой: бэкап, scp, py_compile на VPS, рестарт, прогон, проверка лога.
- Через неделю — `source_report.py`, сверить, что отключённое не дало полезных.
- Токен Kraken неизвестен (404), при случае выяснить.

## Дополнение: гео-фильтр и SEA-борды

Найдено при проверке 150+ брокеров, маркет-мейкеров и финтехов на 6 ATS: у брокеров
и торговых платформ операционные роли почти всегда привязаны к офису и лицензии.
Pepperstone (Лимасол, Сантьяго), Swissquote (Мальта, Люксембург), Nasdaq (США),
Devexperts (Тбилиси, hybrid in Georgia) — ни одной remote-ops-вакансии.

При этом на наших же бордах 79% вакансий оказались onsite:
Coinbase 23 remote / 3 onsite, Alpaca 8/1, Bybit 2/22, OKX 0/21, Binance 0/30,
Robinhood 0/11, Adyen 0/25, Bitpanda 0/6, Bitgo 0/5, B2C2 0/2.

Поэтому:

- `sources.json` → `eligibility`: home-city (Bangkok/Thailand) сохраняется даже onsite,
  остальное должно быть remote и не залочено на страну/город.
- Проверка реализована позитивно: из локации вырезаются generic-слова
  (remote, global, APAC, EMEA, anywhere, hybrid, world...), и если что-то осталось,
  это конкретное место → отбрасываем. Так «Remote - London» и «Remote - Japan»
  не проходят без перечисления всех городов мира. `Remote - US` ловится отдельно:
  остаток «us» не пустой.
- Калибровка: 24 кейса, 0 расхождений.
- Добавлены борды с азиатскими ops-ролями: xendit (платежи SEA, Бангкок),
  thunes (платежи, Манила), stripe (роль в Бангкоке), airwallex (риск и ops, APAC).

Первый прогон: отброшено 253 greenhouse + 3 lever + 47 ashby = 303 вакансии,
к скорингу 7 вместо 98. Результат по fit: Operations Specialist - Gulf Binance
(Thailand) 71, Risk Operations Analyst 65 (Stripe, remote), Financial Operations
Associate 59 (Xendit, Bangkok).

Найдены три вакансии в Бангкоке — по географии это лучший результат за сессию,
так как снимает проблему часового пояса и права на работу.
