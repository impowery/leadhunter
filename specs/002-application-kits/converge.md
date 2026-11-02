# Converge

## Сделано
- build_application_kit: один LLM-вызов, JSON с letter и answers.
- send_application_kits: только владелец, fit >= 60 или recommend, лимит 3, дедуп.
- send_owner_message и send_tg_document: отдельная отправка владельцу и CV файлом.
- Хук в run() вместо старых черновиков send_applications.
- PROFILE_TEXT дополнен: английский, ссылки, часовой пояс, доступность.
- Проверено: письмо по вакансии HousingCare (fit 94), ответы без hedging, тестовый пакет доставлен.

## Открыто
- Залить обновлённый CV (docx) в resume на VPS.
- Автозаполнение форм (Playwright) для Greenhouse/Lever/Workable.
- Стадии откликов: interview, offer, rejected.

## Замечания
- При длинных цитатах JSON обрезался: добавлено ограничение 12 слов на цитату и лимит 900 токенов.
