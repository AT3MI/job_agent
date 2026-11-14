"""Слой-лингвист: точечная правка формулировок поверх готового письма.

Дизайн (важно):
- в коде НЕТ лингвистических правил; вся оценка качества — на стороне модели;
- модель видит все редактируемые поля и возвращает закрытый список дефектов
  (repetition / grammar / tautology / fragment) с ДОСЛОВНЫМ quote и fixed
  (исправленное полное предложение, не абзац);
- код применяет правки хирургически: замена quote -> fixed, ровно одно вхождение,
  с инвариантами: числа сохраняются, ссылки/контакты не появляются, длина ограничена,
  заголовок unique_block заморожен, правка не дублирует 3+ подряд слов из другого
  предложения этого же поля (trigram-guard против «запихивания» повтора);
- верификация вторым вызовом опциональна: по умолчанию её роль несут инварианты
  применения + validate_standard + снапшот-откат в generate_letter;
- любой сбой API/парсинга => слой пропускается, письмо не портится (fallback-safe).

Отключение слоя целиком: SKIP_LINGUIST=1 (проверяется в generate_letter).
Верификация вторым вызовом: VERIFY_LINGUIST=1 (по умолчанию выключена).
Trigram-guard: TRIGRAM_GUARD=0 выключает (по умолчанию включён).
Откат уровня кода: git (baseline-коммит до внедрения слоя).
"""

import json
import os
import re

from config.schemas import EditReview, LinguisticVerdict, StandardOutput
from config.identity import PHONE

MAX_ISSUES = 6
MAX_OUTPUT_TOKENS_CHECK = 2500
MAX_OUTPUT_TOKENS_VERIFY = 1500

QUOTE_MIN_LEN = 10
QUOTE_MAX_LEN = 300

# Trigram-guard: правка не должна дублировать 3+ подряд слов из другого
# предложения того же поля («запихивание» повтора на новое место).
# Это защита данных (в ряду инварианта чисел), а не лингвистическое правило.
MAX_NGRAM_OVERLAP = 0


def _trigram_guard_enabled() -> bool:
    return os.environ.get("TRIGRAM_GUARD", "") != "0"


def _verify_enabled() -> bool:
    return os.environ.get("VERIFY_LINGUIST", "") == "1"

_SCALAR_FIELDS = (
    "intro",
    "vacancy_interest",
    "best_solution",
    "unique_block",
    "medtech_experience",
    "why_you",
)

_PROJECT_FIELD_RE = re.compile(r"projects\[(\d+)\]\.(problem|result)")

# Пара problem/result одного проекта: guard сравнивает правку с соседним полем,
# т.к. тавтология «результат пересказывает проблему» живёт между двумя полями.
_SIBLING_FIELD_RE = re.compile(r"^projects\[(\d+)\]\.(problem|result)$")


def _sibling_field(name: str) -> str | None:
    m = _SIBLING_FIELD_RE.fullmatch(name)
    if not m:
        return None
    other = "problem" if m.group(2) == "result" else "result"
    return f"projects[{m.group(1)}].{other}"


def editable_fields(output: StandardOutput) -> dict[str, str]:
    """Редактируемые поля с текстом. closing/контакты, имена и ссылки проектов — вне схемы."""
    fields: dict[str, str] = {name: getattr(output, name) for name in _SCALAR_FIELDS}
    for i, project in enumerate(output.projects):
        fields[f"projects[{i}].problem"] = project.problem
        fields[f"projects[{i}].result"] = project.result
    return {name: text for name, text in fields.items() if text.strip()}


LINGUIST_PROMPT = """Ты — корректор русского языка. Ты НЕ автор письма и НЕ редактор стиля.
Ниже поля сопроводительного письма (JSON: ключ — ID поля, значение — текст).
Найди дефекты строго четырёх типов и верни JSON по схеме LinguisticVerdict.

=== ТИПЫ ДЕФЕКТОВ (только эти четыре) ===
1. repetition — повтор формулировки вблизи, звучащий как ошибка. Три вида:
   а) задвоение («отдельно — отдельно»);
   б) повтор фразы из 2+ значимых слов между СОСЕДНИМИ предложениями одного абзаца;
   в) повтор корня слова в разных формах («полному циклу» ↔ «полным циклом»).
   Живой пример (б)+(в): заголовок «По производственным данным и полному циклу ML — отдельно.»
   ↔ следующее предложение «С данными работаю полным циклом:...». Заголовок «По … — отдельно.» —
   тоже предложение абзаца: правится ПРЕДЛОЖЕНИЕ-ТЕЛО (повтор исчезает в нём), заголовок
   остаётся дословно. Замороженность заголовка — НЕ повод пропускать такой дефект.
   Повтор служебного/частого слова («данных», «работы»), где фраза читается нормально, — НЕ дефект.
   Но термин, повторившийся в соседних предложениях (даже «рабочий» термин вроде «полный цикл»),
   — дефект: переформулируйте одно из мест (то, которое не зачин).
2. grammar — предложение построено вопреки грамматике русского языка:
   «Я был инженер-разработчик» (нужно: инженером-разработчиком);
   «...задачами, где проводятся обследование производственных участков, формализация задач...» —
   после «где» однородные существительные без глагола; нужно личное сказуемое и согласование:
   «...задачами, где смогу обследовать производственные участки, формализовать задачи...».
3. tautology — два предложения сообщают одно и то же; типовой случай — пара
   «Проблема/Результат» проекта:
   Проблема: «...требовался полный цикл от моделирования до интерфейса» /
   Результат: «Реализован полный цикл: от моделирования... до интерфейса».
   Править РЕЗУЛЬТАТ: сформулировать его заново — что сделано и какой получен эффект —
   БЕЗ заимствования формулировки проблемы. Пример ЗАПРЕЩЁННОЙ правки:
   Проблема «Требовалось оценить эффективность методов фильтрации на реальном сигнале» →
   Результат «Проведена оценка эффективности методов фильтрации на реальном сигнале» —
   это дословный пересказ проблемы: вы создали тавтологию вместо правки.
   Проверяйте свою правку: если 2+ значимых слова из fixed уже есть в problem того же
   проекта — переформулируйте. Новых фактов не добавлять.
4. fragment — бессмыслица или обрывок мысли, у фразы нет связи с предложением:
   «...задачами, где обследование производственных участков, формализация задач...» —
   после «где» нет глагола.

=== ЭТО НЕ ДЕФЕКТ — НЕ ТРОГАЙ ===
- необычные, но грамматичные и осмысленные формулировки;
- стиль, длину, порядок предложений, канцелярит;
- повтор служебных/частых слов там, где фраза читается нормально;
- факты, числа, названия компаний и проектов, ссылки;
- эмфазу и повторы-приёмы.

=== ПРОЦЕДУРА САМОПРОВЕРКИ (в этом порядке) ===
1. Для каждого поля сравните КАЖДУЮ пару соседних предложений: общий корень слова или
   общая фраза 2+ значимых слов? Это кандидат в repetition (отфильтруйте по «НЕ ДЕФЕКТ»).
2. Для каждого проекта сравните problem и result: пересказывает ли result problem
   теми же словами? Это tautology.
3. Только после этого ищите grammar/fragment внутри отдельных предложений.

=== ЗАЧИНЫ (заголовки абзацев) ===
Первое предложение абзаца — зачин. Его формулировка задана и не переписывается:
- intro: «Здравствуйте, я молодой специалист...»;
- vacancy_interest: всё до «где ...» фиксировано («Меня заинтересовала ваша вакансия ... и задачами,»),
  править можно только конкретику после «где»;
- best_solution: «По опыту работы с данными и ML. Моё лучшее внедрённое решение:»;
- unique_block: «По [главное требование вакансии] — отдельно.» — формат фиксирован полностью;
- medtech_experience: «Также есть коммерческий опыт работы со сложной тех. документацией.»;
- why_you: «Почему именно к вам.»
Если дефект — конфликт (повтор/тавтология) между зачином и обычным предложением,
правь ОБЫЧНОЕ предложение; зачин не меняй.
Единственное исключение: если ВНУТРИ зачина есть грамматический обрывок (grammar/fragment),
исправь минимально только дефектную фразу, сохранив остальной текст зачина посимвольно.

=== ПРАВИЛА ПРАВКИ ===
- quote — ДОСЛОВНЫЙ фрагмент (10–200 символов) из указанного поля, копируй посимвольно;
- fixed — полное исправленное ПРЕДЛОЖЕНИЕ (не абзац), минимальная правка внутри него;
- меняется только фраза-дефект; соседние предложения не трогаются;
- повтор не переносится: правка не вводит обороты, уже встречающиеся в этом же поле
  или в других полях письма (кроме терминов самой вакансии), и не заменяет старый
  повтор новым — повтор исчезает внутри дефектной фразы;
- не меняй факты, числа, названия, ссылки; ничего не добавляй;
- field — ID поля из JSON ниже; для проектов: projects[0].problem, projects[1].result и т.д.;
- максимум 6 issues — самые грубые; каждый проверь по списку «ЭТО НЕ ДЕФЕКТ»;
- если дефектов нет — верни issues: [] (это нормальный ответ).

=== ПОЛЯ ПИСЬМА ===
{fields_json}
"""


VERIFY_PROMPT = """Ты — корректор русского языка, проверяешь применённые правки письма.
Для каждой правки указаны: поле, «было» (фрагмент до правки), «стало» (фрагмент после).
Проверь каждую правку и верни JSON по схеме EditReview: по одной записи на правку,
в поле was — ДОСЛОВНО значение «было» из списка.
Правка верна (ok=true), только если ВСЁ из списка выполнено:
1) изменена только дефектная фраза; зачин (первое предложение абзаца) не переписан;
2) факты, числа, названия сохранены, ничего нового не добавлено;
3) фраза «стало» грамматически корректна, осмысленна и не вносит новый дефект
   (повтор слова/корня, тавтология, обрывок);
4) стиль письма не изменился.
Если сомневаешься — ok=false.

=== ПРАВКИ ===
{edits_json}
"""


def _quote_pattern(quote: str) -> re.Pattern:
    """Regex из дословного quote с гибкостью по тире и пробелам (нормализация, не правило)."""
    parts = []
    for ch in quote:
        if ch == "—":
            parts.append("[—–-]")
        elif ch in (" ", "\n", "\t"):
            parts.append(r"\s+")
        else:
            parts.append(re.escape(ch))
    return re.compile("".join(parts), flags=re.IGNORECASE)


def _digit_runs(text: str) -> list[str]:
    return re.findall(r"\d+", text)


_WORD_RE = re.compile(r"[а-яёa-z0-9]+")
_SENT_RE = re.compile(r"[^.!?]*[.!?]+|[^.!?]*$")


def _trigrams(text: str) -> set[tuple[str, ...]]:
    words = _WORD_RE.findall(text.lower())
    return set(zip(words, words[1:], words[2:]))


def _overlap_ngrams(text: str, span: tuple[int, int], fixed: str) -> set[tuple[str, ...]]:
    """Общие 3-граммы fixed и ДРУГИХ предложений поля (вне span).

    Предложение, содержащее правку, исключено целиком: минимальная правка законно
    сохраняет слова своей фразы и её соседей по предложению.
    """
    grams: set[tuple[str, ...]] = set()
    for m in _SENT_RE.finditer(text):
        if m.start() < span[1] and m.end() > span[0]:
            continue
        grams |= _trigrams(m.group(0))
    return grams & _trigrams(fixed)


def _reject_reason(issue, field: str, text: str, match: re.Match, sibling_text: str = "") -> str | None:
    """Инварианты правки. Возвращает строку-причину отказа или None."""
    if not (QUOTE_MIN_LEN <= len(issue.quote) <= QUOTE_MAX_LEN):
        return "quote_size: длина фрагмента вне диапазона"
    if issue.field == "unique_block":
        # Заголовок unique_block фиксируется кодом (ensure_unique_block_format),
        # модели он не доступен для правки.
        dot = text.find(".")
        header_end = dot + 1 if dot != -1 else len(text)
        if match.start() < header_end:
            return "frozen_header: заголовок unique_block не редактируется"
    fixed = issue.fixed.strip()
    if not fixed:
        return "empty_fixed: пустая правка"
    if sorted(_digit_runs(issue.quote)) != sorted(_digit_runs(fixed)):
        return "digits_changed: числа в правке не совпадают с исходными"
    if ("http" in fixed.lower()) and ("http" not in issue.quote.lower()):
        return "link_added: правка добавляет ссылку"
    if (PHONE in fixed) or ("vk.ru" in fixed.lower()):
        return "contact_added: правка добавляет контакты"
    limit = max(int(len(issue.quote) * 1.6), len(issue.quote) + 40)
    if len(fixed) > limit:
        return "too_long: правка не минимальна"
    if _trigram_guard_enabled():
        overlap = _overlap_ngrams(text, (match.start(), match.end()), fixed)
        if len(overlap) > MAX_NGRAM_OVERLAP:
            sample = " ".join(sorted(overlap)[0])
            return f"ngram_overlap: правка повторяет 3+ слов из другого предложения поля («{sample}»)"
        if sibling_text:
            cross = _trigrams(fixed) & _trigrams(sibling_text)
            if len(cross) > MAX_NGRAM_OVERLAP:
                sample = " ".join(sorted(cross)[0])
                return (
                    "ngram_overlap_cross: правка дословно пересказывает соседний "
                    f"проект-поле (problem/result) («{sample}»)"
                )
    return None


def _set_field(output: StandardOutput, name: str, value: str) -> None:
    m = _PROJECT_FIELD_RE.fullmatch(name)
    if m:
        setattr(output.projects[int(m.group(1))], m.group(2), value)
    else:
        setattr(output, name, value)


def _call(client, prompt: str, schema, max_tokens: int):
    parsed, call_meta = client.generate_structured(
        prompt,
        schema,
        max_output_tokens=max_tokens,
        apply_budget=False,
    )
    usage = (call_meta or {}).get("tokens") or {}
    return parsed, int(usage.get("total_tokens") or 0)


def run_linguist(client, output: StandardOutput) -> tuple[StandardOutput, dict]:
    """Проверка + хирургические правки (+ верификация при VERIFY_LINGUIST=1).
    Никогда не бросает исключений: при сбое возвращает письмо без изменений
    и meta с описанием ошибки."""
    meta: dict = {
        "calls": 0,
        "tokens": 0,
        "issues_reported": 0,
        "applied": 0,
        "rejected": [],
        "verified": 0,
        "reverted": 0,
        "verify_mode": "off",
        "edits": [],
    }
    try:
        return _run_linguist_inner(client, output, meta)
    except Exception as exc:  # noqa: BLE001 — слой не должен ломать пайплайн
        meta["error"] = f"{type(exc).__name__}: {exc}"
        return output, meta


def _run_linguist_inner(client, output: StandardOutput, meta: dict) -> tuple[StandardOutput, dict]:
    fields = editable_fields(output)
    if not fields:
        meta["skipped"] = "нет непустых редактируемых полей"
        return output, meta

    prompt = LINGUIST_PROMPT.format(fields_json=json.dumps(fields, ensure_ascii=False, indent=2))
    verdict, tokens = _call(client, prompt, LinguisticVerdict, MAX_OUTPUT_TOKENS_CHECK)
    meta["calls"] += 1
    meta["tokens"] += tokens
    meta["issues_reported"] = len(verdict.issues)

    texts: dict[str, str] = dict(fields)
    edits: list[dict] = []
    for issue in verdict.issues[:MAX_ISSUES]:
        text = texts.get(issue.field)
        if text is None:
            meta["rejected"].append({"field": issue.field, "reason": "field_not_editable"})
            continue
        pattern = _quote_pattern(issue.quote)
        m = pattern.search(text)
        if m is None:
            meta["rejected"].append(
                {"field": issue.field, "quote": issue.quote[:80], "reason": "quote_not_found"}
            )
            continue
        sibling = _sibling_field(issue.field)
        sibling_text = texts.get(sibling, "") if sibling else ""
        reject = _reject_reason(issue, issue.field, text, m, sibling_text)
        if reject:
            meta["rejected"].append({"field": issue.field, "quote": issue.quote[:80], "reason": reject})
            continue
        edits.append(
            {
                "field": issue.field,
                "quote": issue.quote,
                "fixed": issue.fixed.strip(),
                "span": m.group(0),
                "before": text,
            }
        )
        texts[issue.field] = text[: m.start()] + issue.fixed.strip() + text[m.end():]

    if not edits:
        return output, meta

    # Верификация применённых правок вторым вызовом — опциональна. По умолчанию
    # выключена: её роль несут инварианты применения (включая trigram-guard),
    # validate_standard после правок и снапшот-откат в generate_letter.
    # VERIFY_LINGUIST=1 возвращает двухвызовную схему без правок кода.
    # Сбой верификации => правки остаются, но помечаются как непроверенные.
    review_map: dict[str, object] = {}
    if _verify_enabled():
        meta["verify_mode"] = "llm"
        try:
            edits_json = json.dumps(
                [{"field": e["field"], "было": e["span"], "стало": e["fixed"]} for e in edits],
                ensure_ascii=False,
                indent=2,
            )
            review, tokens = _call(
                client,
                VERIFY_PROMPT.format(edits_json=edits_json),
                EditReview,
                MAX_OUTPUT_TOKENS_VERIFY,
            )
            meta["calls"] += 1
            meta["tokens"] += tokens
            for v in review.verdicts:
                review_map[v.was] = v
        except Exception as exc:  # noqa: BLE001
            meta["verify_error"] = f"{type(exc).__name__}: {exc}"

    kept: list[dict] = []
    reverted: list[dict] = []
    for edit in edits:
        verdict_item = review_map.get(edit["span"]) or review_map.get(edit["quote"])
        if verdict_item is not None and not verdict_item.ok:
            reverted.append(edit)
        else:
            kept.append(edit)
    # Откат в обратном порядке: «before» поздней правки включает изменения ранних.
    for edit in reversed(reverted):
        texts[edit["field"]] = edit["before"]

    for name, text in texts.items():
        _set_field(output, name, text)

    meta["applied"] = len(kept)
    meta["reverted"] = len(reverted)
    meta["verified"] = len(review_map)
    meta["edits"] = [
        {
            "field": e["field"],
            "quote": e["quote"],
            "fixed": e["fixed"],
            "status": "reverted" if e in reverted else "applied",
        }
        for e in edits
    ]
    return output, meta
