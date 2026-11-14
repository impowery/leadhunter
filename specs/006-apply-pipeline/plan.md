# Plan 006

## Шаги

1. `profile.json`: добавить `bio`, `skills` (строка через запятую, под лимит поля 255).
2. `autofill.py`:
   - `FIELD_MAP`: ключи `bio`, `skills` (`about you`, `tell your story`, `skills`, `expertise`).
   - `type_into()`: для tag-инпутов ввод по одному тегу с Enter; для обычного textarea — целиком.
   - `open_apply_form(page, url)`: Greenhouse/Ashby/Workable/Lever.
   - `letter_for(url, profile)`: кэш `letters/<sha1>.txt` → SSH при промахе.
   - `applied.json`: `is_applied()`, `mark_applied()`, флаги `--mark`, `--force`.
   - `--steps N`: клики «Continue/Next» до N раз, Submit исключён по списку слов.
   - Рефакторинг `main()` в `run(url, ...)`, чтобы вызывать из `next.py`.
3. `apply/queue.py`: SSH-запрос в SQLite на VPS (read-only), выборка лидов с письмом,
   фильтр по `applied.json`, запись `queue.json`.
4. `apply/next.py`: кэш очереди → первая неотправленная → письмо в `last_letter.txt` →
   `autofill.run()` → вопрос «пометить отправленной?».
5. `apply/next.bat`: запуск двойным кликом.
6. `.gitignore`: `apply/letters/`, `apply/queue.json`, `apply/applied.json`,
   `apply/last_letter.txt`, `apply/last_fill.png`.

## Порядок проверки

1. `python -m py_compile` на все изменённые файлы.
2. Оффлайн: кэш письма (два вызова, второй без SSH), лог (mark → is_applied → повторный
   запуск пропускает), разбор очереди на синтетическом JSON.
3. Живьём: `AUTOFILL_HEADLESS=1 python autofill.py <alpaca-url> --steps 1`
   → ожидаем заполненные имя/email/телефон/bio/skills, скриншот, отсутствие Submit.

## Риски

- Разные ATS по-разному помечают поля: возможны пропуски, они попадают в `Skipped`.
- Tag-инпут skills может требовать Enter или запятую: обрабатываем оба варианта.
- SSH к VPS по ключу: если ключ недоступен, очередь не собирается, письмо не тянется —
  скрипт сообщает об этом и продолжает без письма.
