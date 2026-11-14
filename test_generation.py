from src.generation.standard import generate_letter, load_job, load_allowed_facts
from src.generation.assemble import assemble_letter

if __name__ == "__main__":
    job = load_job("job.txt")
    facts = load_allowed_facts()
    print("Генерирую письмо...")
    letter, meta = generate_letter(job)

    final_text = assemble_letter(letter, facts)

    print("\n" + "=" * 60)
    print("ИТОГОВОЕ ПИСЬМО")
    print("=" * 60)
    print(final_text)
    print("=" * 60)

    print("\n=== МЕТАДАННЫЕ ===")
    print(f"Время: {meta['elapsed_sec']} сек")
    print(f"Токены: {meta['tokens']}")
    print(f"Retry: {meta['retry_attempts']}")
    print(f"Ошибки валидации: {len(meta['validation_errors'])}")
    if meta['validation_errors']:
        for e in meta['validation_errors']:
            print(f"  - {e}")
    print(f"Статистика: {meta['stats']}")
    print("\n=== ЛИНГВИСТ ===")
    print(meta.get('linguistic'))