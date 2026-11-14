import os
import time
from typing import TypeVar

from dotenv import load_dotenv
from gigachat import GigaChat
from pydantic import BaseModel

from config.paths import ENV_PATH, resolve_project_path
from config.schemas import StandardOutput

load_dotenv(ENV_PATH)

# --- Бюджет токенов ---
TOKEN_BUDGET_PER_LETTER = 15000  # максимум на одно письмо (вход + выход)

T = TypeVar("T", bound=BaseModel)


def _resolve_ca_bundle() -> str | None:
    """Превращает относительный путь к CA-бандлу в абсолютный."""
    value = os.getenv("GIGACHAT_CA_BUNDLE_FILE")
    if not value:
        return None
    return str(resolve_project_path(value))


class GigaChatClient:
    def __init__(self):
        self.giga = GigaChat(
            base_url="https://api.giga.chat/v1",
            credentials=os.getenv("GIGACHAT_CREDENTIALS"),
            scope="GIGACHAT_API_PERS",
            model="GigaChat-3-Ultra",
            ca_bundle_file=_resolve_ca_bundle(),
            timeout=180,
        )
        self.total_tokens_used = 0
        self.call_count = 0
        self.total_elapsed_sec = 0.0

    def _estimate_tokens(self, text: str) -> int:
        """Оценивает количество входных токенов БЕЗ отправки в модель."""
        try:
            return self.giga.tokens_count([text])[0].tokens
        except Exception:
            # fallback: ~4 символа на токен
            return len(text) // 4

    def _truncate_to_budget(self, text: str, budget: int) -> str:
        """Обрезает текст до бюджета токенов (простая эвристика по символам)."""
        if budget <= 0:
            return "[...промпт не помещается в бюджет...]"
        estimated = self._estimate_tokens(text)
        if estimated <= budget:
            return text
        # обрезаем пропорционально
        ratio = budget / estimated
        cut_len = int(len(text) * ratio * 0.9)  # запас 10%
        return text[:cut_len] + "\n[...обрезано для бюджета...]"

    def generate_structured(
        self,
        prompt: str,
        response_format: type[T],
        max_output_tokens: int = 4000,
        apply_budget: bool = True,
    ) -> tuple[T, dict]:
        """
        Один вызов GigaChat с принудительной схемой response_format.
        Учитывает вызов, токены и время в общей статистике клиента.

        apply_budget=False используется для коротких retry-промптов, чтобы
        не тратить лишний запрос на оценку токенов.
        """
        input_tokens = 0
        if apply_budget:
            input_tokens = self._estimate_tokens(prompt)
            input_budget = TOKEN_BUDGET_PER_LETTER - max_output_tokens
            if input_tokens > input_budget:
                # В промпте резюме стоит последним, поэтому обрезка хвоста
                # не затрагивает текст вакансии и инструкции.
                prompt = self._truncate_to_budget(prompt, input_budget)
                input_tokens = self._estimate_tokens(prompt)
                print(f"  [budget] промпт обрезан до ~{input_tokens} токенов")

        payload = {
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_output_tokens,
        }

        start = time.time()
        try:
            completion, parsed = self.giga.chat_parse(
                payload,
                response_format=response_format,
                strict=True,
            )
        except Exception as e:
            raise RuntimeError(f"GigaChat generation failed: {type(e).__name__}: {e}")

        elapsed = time.time() - start

        self.call_count += 1
        self.total_elapsed_sec += elapsed

        usage = completion.usage
        if usage:
            self.total_tokens_used += usage.total_tokens
            tokens_info = {
                "prompt_tokens": usage.prompt_tokens,
                "completion_tokens": usage.completion_tokens,
                "total_tokens": usage.total_tokens,
                "cumulative_tokens": self.total_tokens_used,
            }
        else:
            tokens_info = {"total_tokens": None, "cumulative_tokens": self.total_tokens_used}

        metadata = {
            "elapsed_sec": round(elapsed, 2),
            "tokens": tokens_info,
            "call_number": self.call_count,
            "input_estimated_tokens": input_tokens,
        }

        return parsed, metadata

    def generate_standard(
        self,
        prompt: str,
        max_output_tokens: int = 4000,
    ) -> tuple[StandardOutput, dict]:
        """Один вызов GigaChat с принудительной схемой StandardOutput."""
        return self.generate_structured(
            prompt,
            StandardOutput,
            max_output_tokens=max_output_tokens,
            apply_budget=True,
        )

    def get_stats(self) -> dict:
        return {
            "total_calls": self.call_count,
            "total_tokens": self.total_tokens_used,
            "total_elapsed_sec": round(self.total_elapsed_sec, 2),
        }
