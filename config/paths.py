from pathlib import Path

# Корень проекта определяется по расположению файла, а не по текущей рабочей
# директории. Это позволяет запускать скрипты из любого места.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
ENV_PATH = PROJECT_ROOT / ".env"
RESUME_PATH = DATA_DIR / "resume.txt"
FACTS_PATH = DATA_DIR / "allowed_facts.json"
DEFAULT_JOB_PATH = PROJECT_ROOT / "job.txt"


def resolve_project_path(path: str | Path) -> Path:
    """Возвращает абсолютный путь: относительные пути считаются от корня проекта."""
    p = Path(path).expanduser()
    if p.is_absolute():
        return p
    return PROJECT_ROOT / p
