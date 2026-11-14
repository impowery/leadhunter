# Converge 006

Статус: готово, локально, коммит в `apply/` + `specs/`. Деплой не требуется:
прод-бот не менялся, очередь читается из существующей базы на VPS (только чтение).

## Что сделано

- `apply/profile.json`: добавлены `bio` (568 символов) и `skills` (242 символа, под лимит поля 255).
- `apply/autofill.py`:
  - `bio`/`skills` в FIELD_MAP, tag-инпут skills заполняется по одному тегу с Enter.
  - `match_field()`: метка поля приоритетнее name/placeholder, регэксп по границе слова.
    Без этого placeholder «skills you want employers to see» попадал в `company`.
  - Адаптеры ATS: Greenhouse (кнопка Apply), Ashby, Workable, Lever (`/apply`).
  - Кэш письма `letters/<sha1>.txt`; SSH к VPS только при промахе.
  - `applied.json`: `--mark`, `--force`, повторная вакансия не открывается.
  - `--steps N`: «Continue/Next» до N раз, Submit исключён по списку слов.
  - `run()` отделён от CLI, чтобы вызывать из `next.py`.
  - Принимает любой URL со схемой (не только http), `input()` больше не падает без tty.
- `apply/queue_build.py`: очередь из SQLite на VPS (read-only), классификация
  `ats` / `other` / `blocked` (Upwork, LinkedIn, Freelancer, Fiverr, Toptal, Guru,
  PeoplePerHour, Codeable, Workana), сортировка: незаблокированные и высокий fit вперёд.
- `apply/next.py` + `apply/next.bat`: следующая вакансия из очереди, письмо в форму,
  вопрос «отправлено?» → запись в `applied.json`.
- `.gitignore`: `queue.json`, `letters/`, `applied.json`, `last_letter.txt`, `last_fill.png`.

## Проверено

1. `py_compile`: autofill, queue_build, next — OK.
2. Оффлайн: `url_key`, `is_applied`/`mark_applied`, кэш письма (запись/чтение),
   `stale()`, разбор queue.json, фильтр уже отправленных — всё проходит.
3. Локальная тест-форма (`file://`, textarea + tag-инпут): заполнены first/last/email/phone,
   `bio` = 568 символов в DOM, skills = 19 тегов отрендерено, поле очищено после Enter.
4. Живая Greenhouse (Alpaca, headless): клик по Apply сработал, заполнены
   country, email, first_name, last_name, linkedin, location, phone; combos:
   Thailand, Male, Decline, not a protected veteran; CV прикреплён; Submit не нажимался.
5. Очередь с VPS: 20 лидов с готовыми письмами получены, классификация работает.

## Найденные и исправленные по ходу баги

- `apply/queue.py` перекрывал стандартный модуль `queue` (его импортирует Playwright) →
  переименован в `queue_build.py`.
- Подстановка `LIMIT` в SQL-шаблон ломала запрос → шаблон переведён на `str.format`.
- Пропуски в парсинге полей: `company` ловил поле skills через «employers».

## Ограничения

- Submit всегда вручную. LinkedIn/Upwork/Freelancer помечаются `blocked` и пропускаются.
- Площадки не из списка ATS (`other`) заполняются как есть: поля могут не совпасть,
  пропуски видны в строке `Skipped`.
- Кэш письма не инвалидируется при повторной генерации письма ботом: удалять
  `apply/letters/<key>.txt` вручную, если письмо перегенерировано.

## Дополнение: выбор CV под вакансию

- `apply/profile.json` → `cv_variants`: `general`, `trading_ops`, `crypto_ops`, `ai`, `payments`.
  `general` указывает на `C:/Users/Андрей/Desktop/Мои резюме/CV.pdf` (личный мастер-файл,
  правки в нём подхватываются автоматически). Остальные версии лежат в `resume/`.
- `pick_cv()`: счёт совпадений по названию вакансии и URL, при равенстве выигрывает
  слово, которое стоит раньше в заголовке. Ключевые слова матчатся по границе слова:
  без этого «rag» совпадал с «coverage» и Alpaca получала AI-резюме.
- В CLI заголовок берётся из `page.title()` после открытия страницы; в `next.py` —
  из очереди. Флаг `--cv <lane>` переопределяет выбор вручную.

Проверено на 7 заголовках: Crypto Operations → crypto_ops, Middle Office → trading_ops,
Trading Operations → trading_ops, AI Automation (n8n) → ai, Stablecoin Payments → payments,
Backend Python и Marketing → general. Живой прогон на Alpaca прикрепил
`Andrey_Mashkin_Crypto_Operations.pdf`.
