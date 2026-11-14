import re

from config.identity import FULL_NAME, PHONE, VK_URL
from config.schemas import StandardOutput


def normalize_dashes(s: str) -> str:
    """Нормализует тире и пробелы для проверки."""
    # Все виды тире → обычное em dash
    s = re.sub(r"[\u2010\u2011\u2012\u2013\u2014\u2015]", "—", s)
    # Неразрывные пробелы → обычные
    s = s.replace("\u00a0", " ")
    # Множественные пробелы → один
    s = re.sub(r" +", " ", s)
    return s


def validate_standard(output: StandardOutput, job_text: str) -> list[str]:
    errors = []
    job_lower = job_text.lower()

    # vacancy_interest
    vi = output.vacancy_interest.strip()
    if not vi:
        errors.append("vacancy_interest: пустое")
    elif len(vi) < 30:
        errors.append("vacancy_interest: слишком короткое")

    # best_solution
    bs = output.best_solution.strip()
    if not bs:
        errors.append("best_solution: пустое")
    elif not any(c.isdigit() for c in bs):
        errors.append("best_solution: нет цифры/результата")

    # unique_block — с нормализацией тире
    ub_norm = normalize_dashes(output.unique_block.strip())
    if not ub_norm.startswith("По "):
        errors.append("unique_block: не начинается с 'По '")
    if " — отдельно" not in ub_norm:
        errors.append("unique_block: нет ' — отдельно'")

    # closing
    cl = output.closing
    if PHONE not in cl:
        errors.append("closing: нет номера")
    if VK_URL not in cl:
        errors.append("closing: нет ссылки")
    if FULL_NAME not in cl:
        errors.append("closing: нет подписи")
    formats = []
    if "Офисный формат" in cl:
        formats.append("офис")
    if "Гибридный формат" in cl:
        formats.append("гибрид")
    if "Удалённый формат" in cl:
        formats.append("удалёнка")
    if len(formats) > 1:
        errors.append(f"closing: несколько форматов ({formats})")
    if len(formats) == 0:
        errors.append("closing: не указан формат")
    if "не трудоустроен" not in cl.lower():
        errors.append("closing: нет статуса")

    # Проверка: если в вакансии есть офис/на месте, а в closing не офис.
    # job_text передаётся явно, чтобы проверка не зависела от файла на диске.
    if "на месте работодателя" in job_lower or "офис" in job_lower:
        if "Офисный формат" not in cl:
            errors.append("closing: в вакансии есть офис/на месте, но выбран не офис")

    # why_you
    if "у вас есть" in output.why_you.lower():
        errors.append("why_you: пересказ вакансии")

    # projects
    for i, proj in enumerate(output.projects):
        if not proj.name.strip():
            errors.append(f"projects[{i}]: пустое name")
        if not proj.problem.strip():
            errors.append(f"projects[{i}]: пустое problem")
        if not proj.result.strip():
            errors.append(f"projects[{i}]: пустое result")

    return errors
