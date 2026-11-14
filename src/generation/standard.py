import json
import os
import re
from pathlib import Path

from pydantic import BaseModel, Field

from config.paths import FACTS_PATH, RESUME_PATH, resolve_project_path
from config.schemas import ProjectItem, StandardOutput
from config.identity import CONTACTS_TEMPLATE
from src.generation.client import GigaChatClient
from src.generation.linguist import run_linguist
from src.validation.deterministic import validate_standard, normalize_dashes


def load_allowed_facts() -> dict:
    return json.loads(FACTS_PATH.read_text(encoding="utf-8"))


def load_resume() -> str:
    return RESUME_PATH.read_text(encoding="utf-8")


def load_job(path: str | Path = "job.txt") -> str:
    return resolve_project_path(path).read_text(encoding="utf-8")


def detect_work_format(job_text: str) -> str:
    """Определяет формат работы по приоритету: офис > гибрид > удалёнка."""
    jt = job_text.lower()
    if "на месте работодателя" in jt or "офис" in jt:
        return "Офисный формат работы полностью подходит."
    elif "гибрид" in jt:
        return "Гибридный формат работы полностью подходит."
    else:
        return "Удалённый формат работы полностью подходит."


def ensure_unique_block_format(unique_block: str) -> str:
    """Идемпотентно приводит unique_block к формату 'По [требование] — отдельно.'.
    - схлопывает задвоения маркера («отдельно — отдельно» и лишние тире);
    - «По X отдельно.» -> «По X — отдельно.»;
    - не добавляет второй маркер, если он уже стоит."""
    ub = normalize_dashes(unique_block.strip())

    # 1. Схлопнуть любые задвоения слова-маркера (с тире или без).
    ub = re.sub(r"\b(отдельно)\b(?:\s*—?\s*\bотдельно\b)+", r"\1", ub, flags=re.IGNORECASE)
    # Лишние сдвоенные тире после схлопывания.
    ub = re.sub(r"—(?:\s*—)+", "—", ub)

    # 2. Каноничный маркер уже стоит — ничего не менять (идемпотентность).
    if " — отдельно" in ub:
        return ub

    # 3. «По X отдельно.» -> «По X — отдельно.» (убираем висящее слово, ставим тире).
    m = re.match(r"^(По [^.:\n]+?)\s+отдельно\s*([.:])", ub)
    if m:
        return m.group(1) + " — отдельно" + m.group(2) + ub[m.end():]

    # 4. Маркера нет вообще — вставить после первой фразы.
    m = re.match(r"^(По [^.:\n]+)([.:])", ub)
    if m:
        return m.group(1) + " — отдельно." + ub[m.end():]

    return "По главному требованию вакансии — отдельно. " + ub


class SingleFieldOutput(BaseModel):
    value: str = Field(description="Исправленное значение поля")


class ProjectsOutput(BaseModel):
    projects: list[ProjectItem] = Field(description="Исправленный список проектов")


STANDARD_PROMPT = """Ты пишешь сопроводительное письмо под вакансию.
Верни JSON по схеме StandardOutput.

=== НАЧАЛА АБЗАЦЕВ (используй эти формулировки как шаблон) ===

- intro: начинается с "Здравствуйте, я молодой специалист, который владеет свежими знаниями вуза 
  и при этом уже имеет производственный опыт и реальные продукты. Хочу развиваться в [направление]."
  [направление] — из вакансии (ML, CV, R&D, аналитика и т.д.).

- vacancy_interest: начинается с "Меня заинтересовала ваша вакансия [название] — я обладаю сильной 
  математической и технической базой, начинаю раскрывать свои возможности и ищу место с хорошим 
  системным подходом и задачами, где [конкретика из вакансии]."
  [конкретика из вакансии] — 1-2 задачи/требования, которые привлекают.

- best_solution: начинается с "По опыту работы с данными и ML. Моё лучшее внедрённое решение:"
  Далее — один якорный проект подробно: проблема → решение → результат (цифра/эффект).
  В конце — одна фраза о смежных Python-задачах, если они усиливают картину.

- unique_block: начинается с "По [главное требование вакансии] — отдельно."
  ФОРМУЛА (БЕЗ слова "Умею"): "[Что делаю]: [аспекты] — [факт-подтверждение из резюме]."
  Сначала выжимка (что делаю), потом факт (подтверждение). Не наоборот.
  Пример: "С данными работаю полным циклом: аудит источников, чистка и сведение, проверка на корректность — 
  в логистике превратил хаотичные данные в рабочие инструменты."
  2-3 таких блока с подтверждениями. Если есть пробелы — обобщённо "пока не работал".
  Только факты по главному требованию вакансии, не тащи другие темы.

- why_you: начинается с "Почему именно к вам." 
  Далее — личная мотивация: почему эта компания привлекает ЛИЧНО меня.
  Не пересказ "у вас есть...", а свой интерес и вклад.

=== ПРАВИЛА ПО ПОЛЯМ ===

1. intro — 1-2 предложения по шаблону выше.

2. vacancy_interest — 1-2 предложения по шаблону выше.

3. best_solution — по шаблону выше. Проблема → решение → результат (цифра).

4. unique_block — по шаблону выше. Только факты по главному требованию, не тащи другие темы.
   Пример хорошего формата:
   "По CV и работе с данными отдельно. С данными работаю полным циклом: подготовка и разметка данных, 
   разделение на обучение и проверку, метрики качества, анализ ошибок — работал с PyTorch и OpenCV. 
   С изображениями работаю через детекцию объектов: разметка классов, обучение и валидация модели — 
   YOLO для контроля перенакопления отходов, разметка 200 изображений. С обработкой лиц (Landmarks, Liveness), 
   голоса (VAD, ASR, Speaker Recognition) и с dlib/ONNX Runtime пока не работал, но база и мотивация есть, 
   готов разобраться быстро."

5. projects — СПИСОК остальных проектов (кроме best_solution). Каждый:
   name, problem, result, link (URL или пустая строка).

6. medtech_experience — опыт с документацией/медтехом/ГОСТ/стандартами.
   Заполняй ТОЛЬКО если вакансия связана с медтехом, госсектором, промышленностью 
   или требует работы с документацией/стандартами. Иначе — пустая строка "".
   Если заполняешь — раскрывай в 3-4 предложениях, не ужимай:
   начинается с "Также есть коммерческий опыт работы со сложной тех. документацией."
   Далее: "Работал в [компания], разрабатывающей [что]. Я был [должность]: писал [что делал: ТУ, паспорта 
   по ГОСТ, методики тестирования, сборка]. Это дало понимание полного инженерного цикла и того, 
   почему документация и качество — часть продукта."

7. why_you — по шаблону выше.

8. closing — ТРИ части:
   а) Формат работы — вставь ДОСЛОВНО готовую строку: "{format_line}"
      Не переписывай её, не добавляй адреса, графики, формат 5/2.
   б) Статус: "На данный момент не трудоустроен, готов приступить быстро."
   в) Контакты и подпись — ДОСЛОВНО из шаблона ниже.

=== ШАБЛОН КОНТАКТОВ (дословно) ===
{contacts}

ФАКТЫ (только из этого списка):
{allowed_facts}

=== ВАКАНСИЯ ===
{job_text}

=== РЕЗЮМЕ ===
{resume_context}
"""


def _retry_project(client, output, index, errors, job_text):
    """Перезапрашивает один проект и возвращает его на место в списке."""
    current = output.projects[index]
    facts = load_allowed_facts()
    allowed_facts = ", ".join(facts["technical_skills"] + facts["soft_skills"])
    retry_prompt = f"""Исправь один проект в списке сопроводительного письма.
Текущее значение:
{current.model_dump_json(indent=2)}
Ошибки:
{chr(10).join(f"- {e}" for e in errors)}
Верни ТОЛЬКО исправленный проект. Поля name, problem, result, link обязательны;
link — URL или пустая строка. Используй только факты из списка ниже.

=== ФАКТЫ (только из этого списка) ===
{allowed_facts}

=== ВАКАНСИЯ ===
{job_text}

=== РЕЗЮМЕ ===
{load_resume()}
"""
    parsed, _ = client.generate_structured(
        retry_prompt,
        ProjectItem,
        max_output_tokens=1500,
        apply_budget=False,
    )
    output.projects[index] = parsed
    return output


def _retry_projects(client, output, errors, job_text):
    """Перезапрашивает весь список проектов, если индекс проекта неизвестен."""
    facts = load_allowed_facts()
    allowed_facts = ", ".join(facts["technical_skills"] + facts["soft_skills"])
    current = json.dumps(
        [p.model_dump() for p in output.projects],
        ensure_ascii=False,
        indent=2,
    )
    retry_prompt = f"""Исправь список проектов сопроводительного письма.
Текущее значение:
{current}
Ошибки:
{chr(10).join(f"- {e}" for e in errors)}
Верни ТОЛЬКО исправленный список проектов. У каждого проекта обязательны name,
problem и result; link — URL или пустая строка. Используй только факты из списка ниже.

=== ФАКТЫ (только из этого списка) ===
{allowed_facts}

=== ВАКАНСИЯ ===
{job_text}

=== РЕЗЮМЕ ===
{load_resume()}
"""
    parsed, _ = client.generate_structured(
        retry_prompt,
        ProjectsOutput,
        max_output_tokens=2500,
        apply_budget=False,
    )
    output.projects = parsed.projects
    return output


def _retry_field(client, output, field_ref, errors, job_text):
    """
    Перезапрашивает одно проблемное поле. field_ref может быть именем поля
    ("closing") или конкретным элементом списка ("projects[0]").
    """
    field_errors = [e for e in errors if e.split(":")[0].strip() == field_ref]
    if not field_errors:
        return output
    print(f"  [retry] '{field_ref}': {field_errors}")

    project_match = re.fullmatch(r"projects\[(\d+)\]", field_ref)
    if project_match:
        index = int(project_match.group(1))
        if 0 <= index < len(output.projects):
            return _retry_project(client, output, index, field_errors, job_text)
        # Индекс мог измениться после предыдущего retry — обновляем весь список.
        field_ref = "projects"

    if field_ref == "projects":
        return _retry_projects(client, output, field_errors, job_text)

    # Скалярные строковые поля (intro, closing, why_you и т.д.).
    if not hasattr(output, field_ref) or not isinstance(getattr(output, field_ref), str):
        return output

    field_name = field_ref
    if field_name == "closing":
        format_line = detect_work_format(job_text)
        retry_prompt = f"""Верни поле closing ДОСЛОВНО по шаблону ниже.
Скопируй шаблон как есть, без изменений. Не добавляй адреса, графики, формат 5/2.

=== ШАБЛОН CLOSING (скопируй дословно) ===
{format_line}
На данный момент не трудоустроен, готов приступить быстро.
{CONTACTS_TEMPLATE}
"""
    else:
        facts = load_allowed_facts()
        allowed_facts = ", ".join(facts["technical_skills"] + facts["soft_skills"])
        retry_prompt = f"""Исправь поле '{field_name}' сопроводительного письма.
Текущее значение:
{getattr(output, field_name)}
Ошибки:
{chr(10).join(f"- {e}" for e in field_errors)}
Верни ТОЛЬКО исправленное значение. Используй только факты из списка ниже.

=== ФАКТЫ (только из этого списка) ===
{allowed_facts}

=== ВАКАНСИЯ ===
{job_text}

=== РЕЗЮМЕ ===
{load_resume()}
"""

    parsed, _ = client.generate_structured(
        retry_prompt,
        SingleFieldOutput,
        max_output_tokens=1500,
        apply_budget=False,
    )
    setattr(output, field_name, parsed.value)
    return output


def generate_letter(job_text: str, max_retries: int = 2) -> tuple[StandardOutput, dict]:
    facts = load_allowed_facts()
    resume_context = load_resume()
    format_line = detect_work_format(job_text)

    prompt = STANDARD_PROMPT.format(
        contacts=CONTACTS_TEMPLATE,
        allowed_facts=", ".join(facts["technical_skills"] + facts["soft_skills"]),
        resume_context=resume_context,
        job_text=job_text,
        format_line=format_line,
    )
    client = GigaChatClient()
    output, metadata = client.generate_standard(prompt)

    # Пост-обработка: гарантируем " — отдельно" программно
    output.unique_block = ensure_unique_block_format(output.unique_block)

    attempt = 0
    final_errors = []
    while attempt <= max_retries:
        errors = validate_standard(output, job_text)
        if not errors:
            final_errors = []
            break
        print(f"  [validation] попытка {attempt + 1}: {len(errors)} ошибок")
        for e in errors[:3]:
            print(f"    - {e}")
        if attempt == max_retries:
            final_errors = errors
            break
        # Сохраняем точные ссылки на поля: "closing" или "projects[0]".
        problem_refs = {e.split(":")[0].strip() for e in errors}
        for field_ref in sorted(problem_refs):
            output = _retry_field(client, output, field_ref, errors, job_text)
        # После retry снова нормализуем
        output.unique_block = ensure_unique_block_format(output.unique_block)
        attempt += 1

    # --- Слой-лингвист: точечная правка формулировок (отключается SKIP_LINGUIST=1) ---
    linguist_meta: dict = {"enabled": os.getenv("SKIP_LINGUIST", "0") != "1"}
    if linguist_meta["enabled"] and not final_errors:
        snapshot = output.model_copy(deep=True)
        output, linguist_meta = run_linguist(client, output)
        # Повторная гарантия формата заголовка unique_block (функция идемпотентна).
        output.unique_block = ensure_unique_block_format(output.unique_block)
        errors_after = validate_standard(output, job_text)
        if len(errors_after) > len(final_errors):
            # Слой ухудшил структурную валидацию — полный откат к снимку.
            output = snapshot
            linguist_meta["reverted_all"] = True
        else:
            final_errors = errors_after
    metadata["linguistic"] = linguist_meta

    metadata["validation_errors"] = final_errors
    metadata["retry_attempts"] = attempt
    metadata["stats"] = client.get_stats()
    metadata["elapsed_sec"] = round(client.total_elapsed_sec, 2)
    metadata["tokens"] = {
        **metadata.get("tokens", {}),
        "cumulative_tokens": client.total_tokens_used,
        "total_calls": client.call_count,
    }
    return output, metadata
