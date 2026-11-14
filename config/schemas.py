from pydantic import BaseModel, Field
from typing import List, Literal


class ProjectItem(BaseModel):
    name: str = Field(description="Название проекта (как в резюме)")
    problem: str = Field(description="Какую проблему решал")
    result: str = Field(description="Результат: цифра/эффект")
    link: str = Field(description="URL, если есть; иначе пустая строка")


class StandardOutput(BaseModel):
    intro: str = Field(description="1-2 предложения: кто я, что ищу.")
    vacancy_interest: str = Field(description="Почему заинтересовала эта вакансия, чем привлекает.")
    best_solution: str = Field(description="Один якорный проект подробно: проблема → решение → результат.")
    unique_block: str = Field(description="Начинается с 'По [требование] — отдельно.'. 2-3 умения с подтверждениями.")
    projects: List[ProjectItem] = Field(description="Остальные проекты кратко.")
    medtech_experience: str = Field(
        description="Опыт с документацией/медтехом/ГОСТ. ТОЛЬКО если вакансия связана с медтехом, "
                    "госсектором, промышленностью или требует работы с документацией/стандартами. "
                    "Иначе — пустая строка."
    )
    why_you: str = Field(description="Личная мотивация: почему эта компания привлекает ЛИЧНО меня.")
    closing: str = Field(description="Формат (один по приоритету) + статус + контакты и подпись дословно.")


# --- Слой-лингвист: закрытая таксономия дефектов формулировок ---

class LinguisticIssue(BaseModel):
    field: str = Field(
        description="ID поля: intro, vacancy_interest, best_solution, unique_block, "
                    "medtech_experience, why_you, projects[N].problem, projects[N].result"
    )
    defect: Literal["repetition", "grammar", "tautology", "fragment"] = Field(
        description="Тип дефекта строго из закрытого списка"
    )
    quote: str = Field(description="Дословный фрагмент 10-200 символов из этого поля, который исправляется")
    fixed: str = Field(description="Исправленное ПОЛНОЕ предложение (не абзац), минимальная правка")
    reason: str = Field(description="Кратко, одним предложением: почему это дефект")


class LinguisticVerdict(BaseModel):
    issues: List[LinguisticIssue] = Field(
        default_factory=list,
        description="Список дефектов. Пустой список = письмо чистое (нормальный ответ)",
    )


class EditReviewItem(BaseModel):
    was: str = Field(description="Дословное значение 'было' из проверяемой правки")
    ok: bool = Field(description="true, только если правка минимальна, факты сохранены и дефект не внесён заново")
    comment: str = Field(default="", description="Краткий комментарий при ok=false")


class EditReview(BaseModel):
    verdicts: List[EditReviewItem] = Field(default_factory=list, description="По одной записи на каждую правку")
