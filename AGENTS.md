# job_agent_v2

## Главное: текущий план

Сейчас в работе **P0**, затем **P1**. Пункт **Г** (fact-gap config / сверка пробелов) отклонён — не реализовывать.

Перед любой задачей прочитай `docs/PROJECT_STATE.md`: там детальный план, решения, состояние кода и чеклист.

## Память и контекст

- Источник истины — файлы проекта и `docs/PROJECT_STATE.md`, а не история чата.
- При compaction или новой сессии сначала прочитай этот файл и `docs/PROJECT_STATE.md`.
- После значимых изменений обновляй `docs/PROJECT_STATE.md` (статус, решения, следующие шаги).
- Пользовательские решения из state-файла не удалять.

## Что за проект

Python-пайплайн генерации сопроводительного письма под вакансию через GigaChat. Модель возвращает JSON по схеме `StandardOutput`, код собирает письмо и валидирует результат.

## Карта

- `config/schemas.py` — Pydantic-схемы.
- `config/identity.py` — контакты письма из `.env` (плейсхолдеры в публичном репо).
- `config/paths.py` — пути от корня проекта.
- `src/generation/client.py` — GigaChat, бюджет, статистика.
- `src/generation/standard.py` — промпт, генерация, retry.
- `src/generation/assemble.py` — сборка финального текста.
- `src/validation/deterministic.py` — структурная валидация.
- `extract_facts.py` — подготовка `data/allowed_facts.json`.
- `data/resume.txt`, `data/allowed_facts.json`, `job.txt`.
- `test_generation.py` — запуск.

## План

- **Готово (2026-11-14):** single-call лингвист (`VERIFY_LINGUIST=1` — старый verify), trigram-guard, промпт проверки усилен живыми примерами.
- **Готово (упаковка):** публичный репо `job_agent` (MIT, README на русском): контакты из `.env` (`config/identity.py`), персональные данные сняты с учёта git, фиктивные примеры данных, `main.py`, CI (офлайн-тесты), Dockerfile, `README.md` + `docs/`.
- **Готово (повторы, прогон №2):** корневые повторы в repetition, процедура самосканирования, запрет заимствования problem в fixed, cross-field guard (`ngram_overlap_cross`) для пары problem/result.
- **Следующий шаг:** публичная ветка `public-main` создана локально (один чистый коммит) — пушится без checkout: `git push -u origin public-main:main`. Master НЕ пушить (в истории персональные данные). Дальше: COVER_* в локальный `.env`, живой прогон — проверить «полный цикл» и cross-guard, реальные метрики уже в README.

## Инварианты

- `closing` и контакты не менять.
- Не заявлять опыт, которого нет в резюме/фактах.
- `soft_skills_block` берётся из данных, не из модели.
- Не трогать `resume.txt` без необходимости.
- Пункт Г не делать.

## Команды

- Генерация: `python test_generation.py`
- Компиляция: `python -m compileall config src extract_facts.py`
- Живую генерацию запускать только по запросу: она тратит токены API.
