from config.schemas import StandardOutput


def assemble_letter(output: StandardOutput, facts: dict) -> str:
    parts = []

    # 1. intro
    parts.append(output.intro.strip())

    # 2. vacancy_interest
    parts.append(output.vacancy_interest.strip())

    # 3. best_solution (якорь)
    parts.append(output.best_solution.strip())

    # 4. unique_block (специализация)
    parts.append(output.unique_block.strip())

    # 5. medtech_experience (дополнительный релевантный опыт — ПОСЛЕ unique_block)
    if output.medtech_experience.strip():
        parts.append(output.medtech_experience.strip())

    # 6. projects (остальные проекты)
    if output.projects:
        lines = ["Другие проекты:"]
        for i, p in enumerate(output.projects, 1):
            block = [f"{i}. {p.name.strip()}"]
            if p.problem.strip():
                block.append(f"   Проблема: {p.problem.strip()}")
            if p.result.strip():
                block.append(f"   Результат: {p.result.strip()}")
            if p.link.strip():
                block.append(f"   Ссылка: {p.link.strip()}")
            lines.append("\n".join(block))
        parts.append("\n\n".join(lines))

    # 7. soft_skills_block — из данных, не из модели
    if facts.get("soft_skills_block"):
        parts.append(facts["soft_skills_block"])

    # 8. why_you
    parts.append(output.why_you.strip())

    # 9. closing
    parts.append(output.closing.strip())

    return "\n\n".join(parts)