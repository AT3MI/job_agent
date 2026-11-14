import os
import re
from dotenv import load_dotenv
from pydantic import BaseModel, Field
from typing import List
from gigachat import GigaChat

from config.paths import ENV_PATH, FACTS_PATH, RESUME_PATH, resolve_project_path

load_dotenv(ENV_PATH)


def _resolve_ca_bundle() -> str | None:
    """Превращает относительный путь к CA-бандлу в абсолютный."""
    value = os.getenv("GIGACHAT_CA_BUNDLE_FILE")
    if not value:
        return None
    return str(resolve_project_path(value))


# --- Схемы ---
class Project(BaseModel):
    name: str = Field(description="Название проекта (кратко, без префиксов)")
    technologies: List[str] = Field(description="Все технологии проекта")

class Facts(BaseModel):
    technical_skills: List[str] = Field(
        description="ТОЛЬКО технические навыки: языки, библиотеки, фреймворки, инструменты, СУБД. "
                    "Библиотеки Python — отдельные навыки. НЕ включай soft skills и языки."
    )
    soft_skills: List[str] = Field(description="Оставь пустым (заполняется отдельно)")
    projects: List[Project] = Field(
        description="ТОЛЬКО проекты (конкретные задачи с результатом). "
                    "НЕ включай места работы (Аналитик-разработчик, Инженер-разработчик, ООО, компания). "
                    "Не разбивай один проект на части."
    )
    education: str = Field(description="Вуз, факультет, специальность, профиль, год — одной строкой. "
                                       "Обязательно включи профиль/направление, если он указан.")
    soft_skills_block: str = Field(
        default="",
        description="Дословный блок про личные качества из резюме (заполняется отдельно, не моделью)"
    )

class SoftSkills(BaseModel):
    soft_skills: List[str] = Field(
        description="ТОЛЬКО личные качества и поведенческие навыки, явно упомянутые в резюме. "
                    "Короткие формулировки (1-3 слова), без пересказа предложений."
    )

class SoftSkillsCheck(BaseModel):
    issues: List[str] = Field(
        description="Список проблем: перефразирования, мусор (условия, технические навыки), дубли."
    )
    fixed_soft_skills: List[str] = Field(
        description="Исправленный И ДОПОЛНЕННЫЙ список soft skills. "
                    "Добавь пропущенные, если они есть в резюме. Сократи пересказы до 1-3 слов."
    )


# --- Клиент ---
giga = GigaChat(
    base_url="https://api.giga.chat/v1",
    credentials=os.getenv("GIGACHAT_CREDENTIALS"),
    scope="GIGACHAT_API_PERS",
    model="GigaChat-3-Ultra",
    ca_bundle_file=_resolve_ca_bundle(),
    timeout=180,
)

resume_text = RESUME_PATH.read_text(encoding="utf-8")


# --- Вырезание дословного блока личных качеств из резюме ---
def _clean_separator_lines(block: str) -> str:
    """Убирает декоративные линии из подчёркиваний/дефисов и хвостовые пробелы."""
    lines = []
    for line in block.splitlines():
        if re.fullmatch(r"[_\-\s]+", line):
            continue
        lines.append(line.rstrip())
    return "\n".join(lines).strip()


def extract_soft_skills_block(text: str) -> str:
    """Вырезает дословный блок про личные качества из резюме по маркеру."""
    markers = [
        r"Из личных качеств[^\n]*\n?",
        r"Личные качества[^\n]*\n?",
        r"Личные качества:",
    ]
    for marker in markers:
        match = re.search(marker, text, re.IGNORECASE)
        if match:
            start = match.start()
            rest = text[start:]
            # Конец — двойной перенос или строка, похожая на заголовок (короткая, без точки)
            end_match = re.search(r"\n\s*\n", rest)
            if end_match:
                block = rest[:end_match.start()]
            else:
                block = rest
            block = _clean_separator_lines(block)
            if len(block) > 20:  # не пустой
                return block
    return ""


# --- Промпты ---
prompt_main = f"""Извлеки из резюме структурированные факты. Верни ТОЛЬКО JSON по схеме.

1. technical_skills — ТОЛЬКО технические навыки: языки, библиотеки, фреймворки, инструменты, СУБД.
   Библиотеки Python (NumPy, Pandas, Matplotlib, Scikit-learn, PyTorch, OpenCV) — 
   ОТДЕЛЬНЫЕ навыки, выделяй каждую.
   НЕ включай soft skills, языки и математические дисциплины.

2. soft_skills — оставь пустым списком.

3. projects — ТОЛЬКО проекты: конкретные задачи с результатом. 
   НЕ включай места работы (Аналитик-разработчик, Инженер-разработчик, ООО, компания).
   НЕ разбивай один проект на части.
   technologies — ВСЕ конкретные инструменты проекта. Если технологий нет — оставь пустым.

4. education — одной строкой: вуз, факультет, специальность, профиль/направление, год. 
   Обязательно включи профиль/направление, если он указан. Не сокращай профиль.

=== РЕЗЮМЕ ===
{resume_text}
"""

soft_prompt = f"""Извлеки из резюме ТОЛЬКО личные качества и поведенческие навыки (soft skills).
Формулировки — короткие (1-3 слова), без пересказа предложений.
НЕ включай: технические навыки, математические дисциплины, языки, 
условия («готовность к командировкам», «готовность к релокации»).
Включай ВСЕ soft skills, которые явно упомянуты или описываются в резюме.

=== РЕЗЮМЕ ===
{resume_text}
"""


# --- Multi-run для technical_skills (union) ---
print("Извлекаю технические навыки (3 прогона)...")
all_technical = set()
last_education = ""
first_projects = []

for i in range(3):
    print(f"  Прогон {i+1}/3...")
    try:
        completion, facts = giga.chat_parse(prompt_main, response_format=Facts, strict=True)
        all_technical.update(facts.technical_skills)
        if len(facts.education) > len(last_education):
            last_education = facts.education
        if not first_projects:
            first_projects = facts.projects
    except Exception as e:
        print(f"  [warn] Прогон {i+1} упал: {type(e).__name__}: {e}")


# --- Нормализация технических навыков ---
def normalize_technical(skill: str) -> str:
    s = re.sub(r"\b1C\b", "1С", skill)
    s = re.sub(r"\s*\([^)]*\)", "", s).strip()
    return s

normalized_technical = set()
for s in all_technical:
    normalized_technical.add(normalize_technical(s))


# --- Фильтрация технических навыков ---
# Модель иногда кладёт в technical_skills soft skills, языки и математические
# дисциплины, поэтому чистим результат детерминированно.
NON_TECHNICAL_PATTERNS = [
    re.compile(r"^английский(\s+язык)?$", re.IGNORECASE),
    re.compile(r"^русский(\s+язык)?$", re.IGNORECASE),
    re.compile(r"^математическ", re.IGNORECASE),
    re.compile(r"^теория вероятностей$", re.IGNORECASE),
    re.compile(r"^статистическ", re.IGNORECASE),
    re.compile(r"^аналитическ", re.IGNORECASE),
    re.compile(r"^работа с большим", re.IGNORECASE),
    re.compile(r"^прогнозирование$", re.IGNORECASE),
    re.compile(r"^анализ данных$", re.IGNORECASE),
]

TECH_ALIASES = {
    "open street map api": "OSM API",
    "osm api": "OSM API",
}


def filter_technical_skills(skills: set[str], soft_skills: list[str]) -> list[str]:
    """Убирает из технических навыков soft skills, языки, математику и дубли."""
    soft_lower = {s.strip().lower() for s in soft_skills}
    unique = {}
    for raw in skills:
        skill = raw.strip()
        if not skill:
            continue
        if skill.lower() in soft_lower:
            continue
        if any(pattern.search(skill) for pattern in NON_TECHNICAL_PATTERNS):
            continue
        skill = TECH_ALIASES.get(skill.lower(), skill)
        unique.setdefault(skill.lower(), skill)
    return sorted(unique.values(), key=str.lower)


# --- Soft skills: генерация + самопроверка с дополнением ---
print("Извлекаю soft skills (генерация)...")
soft_raw = []
try:
    completion, soft = giga.chat_parse(soft_prompt, response_format=SoftSkills, strict=True)
    soft_raw = soft.soft_skills
except Exception as e:
    print(f"  [warn] Генерация soft skills упала: {type(e).__name__}: {e}")

if soft_raw:
    print(f"  Получено {len(soft_raw)} soft skills. Проверяю и дополняю...")
    check_prompt = f"""Ниже список soft skills, извлечённых из резюме. Проверь его и ДОПОЛНИ.

КРИТЕРИИ:
1. НЕТ перефразирований: формулировки должны быть КОРОТКИМИ (1-3 слова).
2. НЕТ мусора: не должно быть технических навыков, математики, языков, условий.
3. НЕТ дублей.
4. ДОПОЛНИ: если в резюме есть soft skills, которых нет в списке — добавь их.

Верни исправленный и ДОПОЛНЕННЫЙ список.

=== СПИСОК SOFT SKILLS ===
{chr(10).join(f"- {s}" for s in soft_raw)}

=== РЕЗЮМЕ ===
{resume_text}
"""
    try:
        completion, check = giga.chat_parse(check_prompt, response_format=SoftSkillsCheck, strict=True)
        if check.issues:
            print(f"  Проблемы: {check.issues[:2]}...")
        print(f"  После проверки: {len(check.fixed_soft_skills)} soft skills")
        soft_final = check.fixed_soft_skills
    except Exception as e:
        print(f"  [warn] Проверка упала: {type(e).__name__}: {e}")
        soft_final = soft_raw
else:
    soft_final = []


# --- Пост-обработка проектов ---
WORK_MARKERS = ["аналитик-разработчик", "инженер-разработчик", "ооо ", "компания", "место работы"]
PREFIXES = ["внедрённое решение:", "внедренное решение:", "проект:", "проект "]

def normalize_name(name: str) -> str:
    n = name.strip().lower()
    for p in PREFIXES:
        if n.startswith(p):
            n = n[len(p):].strip()
    return n

def is_work_place(name: str) -> bool:
    n = name.lower()
    return any(m in n for m in WORK_MARKERS)

cleaned_projects = {}
for proj in first_projects:
    if is_work_place(proj.name):
        continue
    norm = normalize_name(proj.name)
    if norm not in cleaned_projects:
        cleaned_projects[norm] = {"name": proj.name.strip(), "technologies": set(proj.technologies)}
    else:
        cleaned_projects[norm]["technologies"].update(proj.technologies)

final_projects = []
for data in cleaned_projects.values():
    norm_techs = set()
    for t in data["technologies"]:
        norm_techs.add(normalize_technical(t))
    final_projects.append(
        Project(name=data["name"], technologies=sorted(norm_techs, key=str.lower))
    )


# --- Вырезаем дословный блок личных качеств ---
soft_skills_block = extract_soft_skills_block(resume_text)
if soft_skills_block:
    print(f"Найден дословный блок личных качеств: {len(soft_skills_block)} символов")
else:
    print("Дословный блок личных качеств не найден (будет пустым)")


# --- Финальный Facts ---
technical_final = filter_technical_skills(normalized_technical, soft_final)

final_facts = Facts(
    technical_skills=technical_final,
    soft_skills=sorted(soft_final, key=str.lower),
    projects=final_projects,
    education=last_education,
    soft_skills_block=soft_skills_block,
)

FACTS_PATH.write_text(
    final_facts.model_dump_json(indent=2), encoding="utf-8"
)

print(f"\nГотово. Технических: {len(final_facts.technical_skills)}, "
      f"Soft: {len(final_facts.soft_skills)}, Проектов: {len(final_facts.projects)}")