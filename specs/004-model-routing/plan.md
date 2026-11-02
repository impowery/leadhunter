# План 004

1. lead_hunter_pro.py: `_env_list()` + четыре списка LLM_*_MODELS; LLM_PRICES — новые цены tokenharbor.
2. `_llm_chain(tier)`: собрать цепочку из списков, дедуп по (id(client), model), groq — хвост.
3. README.md: абзац «Выбор моделей».
4. Проверки: py_compile локально и на VPS; цепочки bulk/quality/escalate; тестовый скоринг через /tmp/bench_models.py; трейсбеков в логе нет.
