# leadhunter
Automatic leadhunter script+bot


## Выбор моделей

Все LLM-вызовы идут через tokenharbor (`TOKENHARBOR_API_KEY`), OpenRouter и Groq — фолбэки.
Тиры в `_llm_chain()`:

- **bulk** (скоринг, много лидов): `LLM_BULK_MODELS` (бесплатные) → `LLM_BULK_PAID_MODELS` → OpenRouter → Groq. Если `LLM_BULK_FREE_FIRST=0`, платные идут первыми.
- **quality** (письма, кит, роутер): `LLM_QUALITY_MODELS` → `LLM_BULK_MODELS` → OpenRouter → Groq.
- **escalate** (повтор, когда дешёвый тир вернул битый JSON): `LLM_ESCALATE_MODELS` → `LLM_QUALITY_MODELS` → `LLM_BULK_MODELS` → OpenRouter → Groq.

Списки задаются через окружение, значения через запятую; старые `LLM_QUALITY_MODEL` / `LLM_ESCALATE_MODEL` ставятся первыми в свой список. Цены для учёта расходов — в `LLM_PRICES`.
