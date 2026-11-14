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
