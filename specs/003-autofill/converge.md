# Converge

## Сделано
- autofill.py: Playwright + системный Chrome, эвристика по name/id/placeholder/label.
- profile.json: имя, email, телефон, локация, страна, LinkedIn, GitHub, сайт, компания,
  ставка, notice, английский, часовой пояс, work authorization (No), sponsorship (Yes), gender (Male),
  veteran status (not a protected veteran), race (Decline).
- fill_application.bat: запуск в один клик, URL из буфера обмена.
- get_letter.py и таблица kits: бот сохраняет письмо по URL, скрипт забирает его по SSH.
- Lever: автопереход на /apply.
- Комбобоксы (react-select): подписи через label[for] и aria-labelledby, выбор варианта.
- Проверка после заполнения, повтор через клавиатуру, отчёт по незаполненным.
- Скриншот формы: apply/last_fill.png.

## Калибровка на живой форме Greenhouse (Ondo Finance)
Заполнено: имя, фамилия, email, телефон, локация, страна, LinkedIn, CV прикреплён.
Комбобоксы: work authorization No, sponsorship Yes, gender Male, race Decline, veteran not a protected veteran.

## Калибровка на Lever (Anchorage Digital)
Заполнено: full name, email, phone, current company, LinkedIn, CV прикреплён.
Current location и GitHub URL кастомные, значение не удерживается, заполняются вручную.

## Открыто
- Телефон на Greenhouse отображается в национальном формате (09892740117), проверить перед Submit.
- Кастомные поля Lever (location, github).
- Автосабмит не делается намеренно.
