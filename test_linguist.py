"""Офлайн-тесты слоя-лингвиста и обвязки unique_block. Без вызовов GigaChat:
клиент подменяется заглушкой, вердикты — заранее заданные объекты схем.

Запуск: python test_linguist.py
"""

import json
import os
import sys
from copy import deepcopy
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from config.schemas import (  # noqa: E402
    EditReview,
    EditReviewItem,
    LinguisticIssue,
    LinguisticVerdict,
    ProjectItem,
    StandardOutput,
)
from config.identity import FULL_NAME, PHONE, VK_URL  # noqa: E402
from src.generation import standard as standard_module  # noqa: E402
from src.generation.linguist import editable_fields, run_linguist  # noqa: E402
from src.generation.standard import ensure_unique_block_format  # noqa: E402

JOB_TEXT = "Требуется инженер-аналитик. Работа в офисе на месте работодателя, полный день."

EXAMPLE_FACTS_PATH = Path(__file__).parent / "data" / "allowed_facts.example.json"
EXAMPLE_RESUME_PATH = Path(__file__).parent / "data" / "resume.example.txt"


def _example_facts() -> dict:
    """Факты из example-файла: тесты самодостаточны и не зависят от локального allowed_facts.json (CI)."""
    return json.loads(EXAMPLE_FACTS_PATH.read_text(encoding="utf-8"))


def _example_resume() -> str:
    return EXAMPLE_RESUME_PATH.read_text(encoding="utf-8")


def make_output() -> StandardOutput:
    return StandardOutput(
        intro=(
            "Здравствуйте, я молодой специалист, который владеет свежими знаниями вуза "
            "и при этом уже имеет производственный опыт и реальные продукты. "
            "Хочу развиваться в ML и Computer Vision."
        ),
        vacancy_interest=(
            "Меня заинтересовала ваша вакансия Data Scientist — я обладаю сильной "
            "математической и технической базой, начинаю раскрывать свои возможности и ищу место "
            "с хорошим системным подходом и задачами, где обследование производственных участков, "
            "формализация задач в цифровые кейсы и внедрение ML-решений с экономическим эффектом."
        ),
        best_solution=(
            "По опыту работы с данными и ML. Моё лучшее внедрённое решение: автоматический "
            "контроль перенакопления отходов ТКО. Разметка 200 изображений, ежедневный поток "
            "4000 фото. Результат: пропуск заваленных площадок полностью исключён."
        ),
        unique_block=(
            "По работе с производственными данными и полному циклу ML — отдельно. "
            "С данными работаю полным циклом: сбор, выгрузка, очистка, анализ, "
            "построение признаков, обучение моделей, внедрение, мониторинг."
        ),
        projects=[
            ProjectItem(
                name="Система прогнозирования загрязнения воздуха",
                problem="Распознавание образов по данным с датчиков, требуется полный цикл от моделирования до интерфейса.",
                result="Реализован полный цикл: от моделирования электротехнической части до алгоритмов распознавания и пользовательского интерфейса.",
                link="https://disk.yandex.ru/d/XKNC0v_wG5PhIA",
            ),
            ProjectItem(
                name="Диплом: сравнение моделей фильтрации данных",
                problem="Требовалось применить математические методы к временным рядам и разобрать результаты.",
                result="Проведено сравнение байесовского классификатора и Random Forest на реальном сигнале.",
                link="https://disk.yandex.ru/d/_GrlZmdueqRSFg",
            ),
            ProjectItem(
                name="Дашборд анализа эффективности рекламной кампании",
                problem="Нужен кастомный инструмент для сбора, обработки и визуализации ключевых метрик кампании.",
                result="Разработано решение на Python: автоматизирован сбор и обработка данных, визуализированы ключевые метрики.",
                link="https://disk.yandex.ru/d/SsE8w0XrX1mcQg",
            ),
        ],
        medtech_experience=(
            "Также есть коммерческий опыт работы со сложной тех. документацией. "
            "Работал в ООО «Медтехника», производящей аппараты ИВЛ. "
            "Я был инженер-разработчик (методист): писал технические условия и паспорта по ГОСТ."
        ),
        why_you=(
            "Почему именно к вам. НЛМК — это масштаб, реальные производственные данные "
            "и культура, где идеи превращаются в эффекты через «Банк идей»."
        ),
        closing=(
            "Офисный формат работы полностью подходит.\n"
            "На данный момент не трудоустроен, готов приступить быстро.\n"
            "Для связи прошу использовать мой личный номер\n"
            f"{PHONE} (Звонок или MAX)\n"
            f"Или сообщения в ВК\n"
            f"{VK_URL}\n"
            "\n"
            f"С уважением,\n"
            f"{FULL_NAME}"
        ),
    )


class StubClient:
    """Заглушка GigaChatClient: отдаёт заранее заданные ответы по очереди."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.prompts: list[str] = []

    def generate_structured(self, prompt, response_format, max_output_tokens=4000, apply_budget=False):
        self.prompts.append(prompt)
        item = self._responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item, {"tokens": {"total_tokens": 100, "cumulative_tokens": 100}}

    def get_stats(self):
        return {"total_calls": len(self.prompts)}


def issue(field, defect, quote, fixed, reason="тест"):
    return LinguisticIssue(field=field, defect=defect, quote=quote, fixed=fixed, reason=reason)


# --- Тесты ensure_unique_block_format ---

UB_CASES = [
    ("По CV и работе с данными отдельно. Текст.", "По CV и работе с данными — отдельно. Текст."),
    ("По CV и работе с данными — отдельно. Текст.", "По CV и работе с данными — отдельно. Текст."),
    ("По CV отдельно — отдельно. Текст.", "По CV — отдельно. Текст."),
    ("По CV — отдельно — отдельно. Текст.", "По CV — отдельно. Текст."),
    ("По CV отдельно отдельно. Текст.", "По CV — отдельно. Текст."),
    ("По CV. Текст.", "По CV — отдельно. Текст."),
    (
        "По работе с производственными данными и полному циклу ML отдельно — отдельно. С данными работаю.",
        "По работе с производственными данными и полному циклу ML — отдельно. С данными работаю.",
    ),
]


def test_ub_format():
    for src, expected in UB_CASES:
        got = ensure_unique_block_format(src)
        check(f"ub_format: {src[:45]}...", got == expected, f"got: {got}")
        twice = ensure_unique_block_format(got)
        check(f"ub_idempotent: {src[:45]}...", twice == expected, f"got: {twice}")


def test_editable_fields():
    out = make_output()
    fields = editable_fields(out)
    names = set(fields)
    expected = {
        "intro", "vacancy_interest", "best_solution", "unique_block",
        "medtech_experience", "why_you",
        "projects[0].problem", "projects[0].result",
        "projects[1].problem", "projects[1].result",
        "projects[2].problem", "projects[2].result",
    }
    check("editable_fields: набор полей", names == expected, f"got: {names ^ expected}")
    out2 = make_output()
    out2.medtech_experience = ""
    check("editable_fields: пустое поле исключено", "medtech_experience" not in editable_fields(out2))


def test_apply_happy_path():
    out = make_output()
    client = StubClient([
        LinguisticVerdict(issues=[issue(
            "unique_block", "repetition",
            "С данными работаю полным циклом: сбор, выгрузка, очистка, анализ,",
            "Данные веду по всему циклу: сбор, выгрузка, очистка, анализ,",
        )]),
        EditReview(verdicts=[EditReviewItem(
            was="С данными работаю полным циклом: сбор, выгрузка, очистка, анализ,",
            ok=True,
        )]),
    ])
    os.environ["VERIFY_LINGUIST"] = "1"
    try:
        _, meta = run_linguist(client, out)
    finally:
        os.environ.pop("VERIFY_LINGUIST", None)
    check("happy: правка применена", "Данные веду по всему циклу" in out.unique_block, out.unique_block[:80])
    check("happy: зачин не тронут", out.unique_block.startswith("По работе с производственными данными и полному циклу ML — отдельно."))
    check("happy: meta applied=1", meta["applied"] == 1, str(meta))
    check("happy: meta reverted=0", meta["reverted"] == 0)
    check("happy: два вызова (check+verify)", meta["calls"] == 2)
    check("happy: verify_mode llm", meta["verify_mode"] == "llm", str(meta))


def test_single_call_default():
    """Дефолтный путь: один вызов, verify выключен; роль верификации — инварианты.
    Заодно проверяет guard: слова хвоста СВОЕГО предложения не считаются повтором."""
    out = make_output()
    client = StubClient([
        LinguisticVerdict(issues=[issue(
            "unique_block", "repetition",
            "С данными работаю полным циклом: сбор, выгрузка, очистка, анализ,",
            "С данными веду работу целиком: сбор, выгрузка, очистка, анализ,",
        )]),
    ])
    _, meta = run_linguist(client, out)
    check("single: правка применена", "С данными веду работу целиком" in out.unique_block, out.unique_block[:80])
    check("single: один вызов", meta["calls"] == 1, str(meta))
    check("single: verify_mode off", meta["verify_mode"] == "off", str(meta))
    check("single: guard не мешал", meta["rejected"] == [], str(meta["rejected"]))


def test_ngram_guard_cross_field_tautology():
    """fixed дословно пересказывает problem того же проекта — отказ (как в живом прогоне)."""
    out = make_output()
    client = StubClient([
        LinguisticVerdict(issues=[issue(
            "projects[1].result", "grammar",
            "Проведено сравнение байесовского классификатора и Random Forest на реальном сигнале.",
            "Применены математические методы к временным рядам и разобраны результаты.",
        )]),
    ])
    _, meta = run_linguist(client, out)
    check("cross_guard: тавтология с problem отброшена", meta["applied"] == 0, str(meta))
    check(
        "cross_guard: причина ngram_overlap_cross",
        any(r["reason"].startswith("ngram_overlap_cross") for r in meta["rejected"]),
        str(meta["rejected"]),
    )
    check("cross_guard: текст не испорчен", "Проведено сравнение байесовского классификатора" in out.projects[1].result)


def test_ngram_guard_cross_field_allows_legit():
    out = make_output()
    client = StubClient([
        LinguisticVerdict(issues=[issue(
            "projects[1].result", "grammar",
            "Проведено сравнение байесовского классификатора и Random Forest на реальном сигнале.",
            "Проведено сравнение двух моделей фильтрации на реальном сигнале.",
        )]),
    ])
    _, meta = run_linguist(client, out)
    check("cross_ok: легальная правка применена", meta["applied"] == 1, str(meta))
    check(
        "cross_ok: правка в тексте",
        "Проведено сравнение двух моделей фильтрации" in out.projects[1].result,
    )


def test_ngram_guard_rejects_stuffing():
    """fixed дублирует 3+ подряд слов из заголовка (другого предложения поля) — отказ."""
    out = make_output()
    client = StubClient([
        LinguisticVerdict(issues=[issue(
            "unique_block", "repetition",
            "С данными работаю полным циклом: сбор, выгрузка, очистка, анализ,",
            "По работе с производственными данными веду весь цикл: сбор, выгрузка, очистка, анализ,",
        )]),
    ])
    _, meta = run_linguist(client, out)
    check("guard: запихивание отброшено", meta["applied"] == 0, str(meta))
    check("guard: причина ngram_overlap", any(r["reason"].startswith("ngram_overlap") for r in meta["rejected"]))
    check("guard: текст не испорчен", "С данными работаю полным циклом" in out.unique_block)


def test_ngram_guard_disabled():
    out = make_output()
    client = StubClient([
        LinguisticVerdict(issues=[issue(
            "unique_block", "repetition",
            "С данными работаю полным циклом: сбор, выгрузка, очистка, анализ,",
            "По работе с производственными данными веду весь цикл: сбор, выгрузка, очистка, анализ,",
        )]),
    ])
    os.environ["TRIGRAM_GUARD"] = "0"
    try:
        _, meta = run_linguist(client, out)
    finally:
        os.environ.pop("TRIGRAM_GUARD", None)
    check("guard_off: применено", meta["applied"] == 1, str(meta))
    check("guard_off: правка в тексте", "По работе с производственными данными веду весь цикл" in out.unique_block)


def test_grammar_fix_inside_header_allowed():
    out = make_output()
    old = "где обследование производственных участков, формализация задач в цифровые кейсы и внедрение ML-решений с экономическим эффектом."
    new = "где смогу обследовать производственные участки, формализовать задачи в цифровые кейсы и внедрять ML-решения с экономическим эффектом."
    client = StubClient([
        LinguisticVerdict(issues=[issue("vacancy_interest", "grammar", old, new)]),
        EditReview(verdicts=[EditReviewItem(was=old, ok=True)]),
    ])
    _, meta = run_linguist(client, out)
    check("grammar_in_header: применено", new in out.vacancy_interest, out.vacancy_interest[:120])
    check("grammar_in_header: зачин сохранён", out.vacancy_interest.startswith("Меня заинтересовала ваша вакансия Data Scientist"))
    check("grammar_in_header: applied=1", meta["applied"] == 1)


def test_quote_not_found():
    out = make_output()
    client = StubClient([
        LinguisticVerdict(issues=[issue("intro", "repetition", "такой фразы здесь нет вообще", "новая фраза")]),
    ])
    _, meta = run_linguist(client, out)
    check("quote_not_found: отброшено", meta["applied"] == 0, str(meta))
    check("quote_not_found: причина записана", meta["rejected"][0]["reason"].startswith("quote_not_found"))
    check("quote_not_found: verify не вызван", meta["calls"] == 1)


def test_frozen_unique_header():
    out = make_output()
    client = StubClient([
        LinguisticVerdict(issues=[issue(
            "unique_block", "repetition",
            "По работе с производственными данными и полному циклу ML — отдельно.",
            "По данным и ML-циклу отдельно.",
        )]),
    ])
    _, meta = run_linguist(client, out)
    check("frozen_header: отброшено", meta["applied"] == 0, str(meta))
    check("frozen_header: причина", any(r["reason"].startswith("frozen_header") for r in meta["rejected"]))


def test_digits_guard():
    out = make_output()
    client = StubClient([
        LinguisticVerdict(issues=[issue(
            "best_solution", "grammar",
            "Разметка 200 изображений, ежедневный поток 4000 фото.",
            "Разметка изображений для ежедневного потока фото.",
        )]),
    ])
    _, meta = run_linguist(client, out)
    check("digits_guard: отброшено", meta["applied"] == 0, str(meta))
    check("digits_guard: причина", any(r["reason"].startswith("digits_changed") for r in meta["rejected"]))


def test_closing_not_editable():
    out = make_output()
    client = StubClient([
        LinguisticVerdict(issues=[issue("closing", "grammar", PHONE, "телефон изменён")]),
    ])
    _, meta = run_linguist(client, out)
    check("closing: не редактируется", meta["applied"] == 0, str(meta))
    check("closing: причина", any(r["reason"].startswith("field_not_editable") for r in meta["rejected"]))


def test_revert_on_verify_fail():
    out = make_output()
    quote = "С данными работаю полным циклом: сбор, выгрузка, очистка, анализ,"
    client = StubClient([
        LinguisticVerdict(issues=[issue("unique_block", "repetition", quote, "Данные веду по всему циклу: сбор, выгрузка, очистка, анализ,")]),
        EditReview(verdicts=[EditReviewItem(was=quote, ok=False, comment="фраза потеряла смысл")]),
    ])
    before = out.unique_block
    os.environ["VERIFY_LINGUIST"] = "1"
    try:
        _, meta = run_linguist(client, out)
    finally:
        os.environ.pop("VERIFY_LINGUIST", None)
    check("revert: текст восстановлен", out.unique_block == before, out.unique_block[:80])
    check("revert: meta reverted=1", meta["reverted"] == 1, str(meta))
    check("revert: статус в edits", meta["edits"][0]["status"] == "reverted")


def test_clean_letter():
    out = make_output()
    client = StubClient([LinguisticVerdict(issues=[])])
    before = out.model_copy(deep=True)
    _, meta = run_linguist(client, out)
    check("clean: без правок", meta["applied"] == 0 and meta["calls"] == 1, str(meta))
    check("clean: письмо не изменено", out == before)


def test_api_failure_fallback():
    out = make_output()
    client = StubClient([RuntimeError("API недоступен")])
    before = out.model_copy(deep=True)
    _, meta = run_linguist(client, out)
    check("api_fail: письмо не тронуто", out == before)
    check("api_fail: ошибка в meta", "error" in meta, str(meta))


def test_generate_letter_integration():
    base = make_output()
    quote = "Я был инженер-разработчик (методист): писал технические условия"
    fixed = "Работал инженером-разработчиком (методистом): писал технические условия"
    verdict = LinguisticVerdict(issues=[issue("medtech_experience", "grammar", quote, fixed)])

    class FakeClient:
        total_tokens_used = 0
        call_count = 0
        total_elapsed_sec = 0.0

        def __init__(self):
            self._responses = [verdict]

        def generate_standard(self, prompt, max_output_tokens=4000):
            return deepcopy(base), {"tokens": {"total_tokens": 100, "cumulative_tokens": 100}}

        def generate_structured(self, prompt, response_format, max_output_tokens=4000, apply_budget=False):
            return self._responses.pop(0), {"tokens": {"total_tokens": 50, "cumulative_tokens": 150}}

        def get_stats(self):
            return {"total_calls": 1}

    fake = FakeClient()
    original_client = standard_module.GigaChatClient
    original_facts = standard_module.load_allowed_facts
    original_resume = standard_module.load_resume
    standard_module.GigaChatClient = lambda: fake
    standard_module.load_allowed_facts = _example_facts
    standard_module.load_resume = _example_resume
    try:
        letter, meta = standard_module.generate_letter(JOB_TEXT)
    finally:
        standard_module.GigaChatClient = original_client
        standard_module.load_allowed_facts = original_facts
        standard_module.load_resume = original_resume
    check("integration: правка medtech применена", fixed in letter.medtech_experience, letter.medtech_experience[:100])
    check("integration: closing не тронут", letter.closing == base.closing)
    check("integration: linguistic.applied=1", meta["linguistic"]["applied"] == 1, str(meta["linguistic"]))
    check("integration: verify выключен по умолчанию", meta["linguistic"]["verify_mode"] == "off", str(meta["linguistic"]))
    check("integration: валидация чистая", meta["validation_errors"] == [], str(meta["validation_errors"]))


def test_generate_letter_skip_flag():
    base = make_output()

    class FakeClient:
        total_tokens_used = 0
        call_count = 0
        total_elapsed_sec = 0.0
        structured_calls = 0

        def generate_standard(self, prompt, max_output_tokens=4000):
            return deepcopy(base), {"tokens": {"total_tokens": 100, "cumulative_tokens": 100}}

        def generate_structured(self, prompt, response_format, max_output_tokens=4000, apply_budget=False):
            self.structured_calls += 1
            raise AssertionError("лингвист не должен вызываться при SKIP_LINGUIST=1")

        def get_stats(self):
            return {}

    fake = FakeClient()
    original_client = standard_module.GigaChatClient
    original_facts = standard_module.load_allowed_facts
    original_resume = standard_module.load_resume
    standard_module.GigaChatClient = lambda: fake
    standard_module.load_allowed_facts = _example_facts
    standard_module.load_resume = _example_resume
    os.environ["SKIP_LINGUIST"] = "1"
    try:
        letter, meta = standard_module.generate_letter(JOB_TEXT)
    finally:
        os.environ.pop("SKIP_LINGUIST", None)
        standard_module.GigaChatClient = original_client
        standard_module.load_allowed_facts = original_facts
        standard_module.load_resume = original_resume
    check("skip: слой выключен", meta["linguistic"]["enabled"] is False, str(meta["linguistic"]))
    check("skip: письмо без изменений", letter.unique_block == base.unique_block)
    check("skip: лингвист не вызывался", fake.structured_calls == 0)


# --- Runner ---

RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    RESULTS.append((name, bool(cond), detail))


def run_all() -> int:
    tests = [
        test_ub_format,
        test_editable_fields,
        test_apply_happy_path,
        test_single_call_default,
        test_ngram_guard_rejects_stuffing,
        test_ngram_guard_disabled,
        test_ngram_guard_cross_field_tautology,
        test_ngram_guard_cross_field_allows_legit,
        test_grammar_fix_inside_header_allowed,
        test_quote_not_found,
        test_frozen_unique_header,
        test_digits_guard,
        test_closing_not_editable,
        test_revert_on_verify_fail,
        test_clean_letter,
        test_api_failure_fallback,
        test_generate_letter_integration,
        test_generate_letter_skip_flag,
    ]
    for t in tests:
        try:
            t()
        except Exception as exc:  # noqa: BLE001
            RESULTS.append((f"{t.__name__}: EXCEPTION", False, f"{type(exc).__name__}: {exc}"))
    failed = [r for r in RESULTS if not r[1]]
    print("=" * 60)
    print(f"ПРОЙДЕНО: {len(RESULTS) - len(failed)} / {len(RESULTS)}")
    for name, ok, detail in RESULTS:
        mark = "PASS" if ok else "FAIL"
        print(f"  [{mark}] {name}" + (f"  -> {detail}" if not ok and detail else ""))
    print("=" * 60)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(run_all())
