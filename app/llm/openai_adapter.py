from openai import OpenAI

from app.llm.base import PROMPT_SISTEMA, DiagnosisContext, build_user_prompt


class OpenAIRenderer:
    name = "openai"

    def __init__(self, api_key: str, model: str, timeout: float = 60.0) -> None:
        self._client = OpenAI(api_key=api_key, timeout=timeout)
        self._model = model

    def render(self, ctx: DiagnosisContext) -> str:
        resp = self._client.responses.create(
            model=self._model,
            instructions=PROMPT_SISTEMA,
            input=build_user_prompt(ctx),
            max_output_tokens=700,
        )
        return resp.output_text
