import httpx

from app.llm.base import PROMPT_SISTEMA, DiagnosisContext, build_user_prompt


class OllamaRenderer:
    name = "ollama"

    def __init__(self, base_url: str, model: str, timeout: float = 60.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout = timeout

    def render(self, ctx: DiagnosisContext) -> str:
        resp = httpx.post(
            f"{self._base_url}/api/chat",
            json={
                "model": self._model,
                "stream": False,
                "messages": [
                    {"role": "system", "content": PROMPT_SISTEMA},
                    {"role": "user", "content": build_user_prompt(ctx)},
                ],
            },
            timeout=self._timeout,
        )
        resp.raise_for_status()
        return resp.json()["message"]["content"]
