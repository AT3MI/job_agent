"""Точка входа: python main.py [путь_к_вакансии.txt]

Генерирует сопроводительное письмо: job.txt → GigaChat → валидация →
слой-лингвист → сборка. Печатает письмо и сохраняет в letter.txt.
"""

import sys
from pathlib import Path

from src.generation.assemble import assemble_letter
from src.generation.standard import generate_letter, load_allowed_facts, load_job

DEFAULT_JOB = "job.txt"
LETTER_OUT = "letter.txt"


def main() -> int:
    job_path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_JOB
    job = load_job(job_path)
    facts = load_allowed_facts()

    print(f"Вакансия: {job_path}")
    print("Генерирую письмо...")
    letter, meta = generate_letter(job)

    final_text = assemble_letter(letter, facts)
    Path(LETTER_OUT).write_text(final_text, encoding="utf-8")

    print("\n" + "=" * 60)
    print("ИТОГОВОЕ ПИСЬМО")
    print("=" * 60)
    print(final_text)
    print("=" * 60)
    print(f"\nПисьмо сохранено: {LETTER_OUT}")

    print("\n=== МЕТАДАННЫЕ ===")
    print(f"Время: {meta['elapsed_sec']} сек")
    print(f"Токены: {meta['tokens']}")
    print(f"Retry: {meta['retry_attempts']}")
    print(f"Ошибки валидации: {len(meta['validation_errors'])}")
    if meta["validation_errors"]:
        for e in meta["validation_errors"]:
            print(f"  - {e}")
    print(f"Статистика: {meta['stats']}")
    print("\n=== ЛИНГВИСТ ===")
    print(meta.get("linguistic"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
