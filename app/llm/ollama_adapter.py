import httpx

from app.llm.base import RenderContext, build_user_prompt, system_prompt_for


class OllamaRenderer:
    name = "ollama"

    def __init__(self, base_url: str, model: str, timeout: float = 60.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout = timeout

    def render(self, ctx: RenderContext) -> str:
        resp = httpx.post(
            f"{self._base_url}/api/chat",
            json={
                "model": self._model,
                "stream": False,
                # format=json obriga o Ollama a devolver JSON parseavel;
                # temperature=0 + seed fixa tornam a mesma pergunta reprodutivel,
                # que e pre-requisito para os evals do Plano 4.
                "format": "json",
                "options": {
                    "temperature": 0,
                    "seed": 42,
                },
                "messages": [
                    {"role": "system", "content": system_prompt_for(ctx)},
                    {"role": "user", "content": build_user_prompt(ctx)},
                ],
            },
            timeout=self._timeout,
        )
        resp.raise_for_status()
        return resp.json()["message"]["content"]
