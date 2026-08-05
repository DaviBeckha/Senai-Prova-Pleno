from openai import OpenAI

from app.llm.base import RenderContext, build_user_prompt, system_prompt_for


class OpenAIRenderer:
    name = "openai"

    def __init__(self, api_key: str, model: str, timeout: float = 60.0) -> None:
        self._client = OpenAI(api_key=api_key, timeout=timeout)
        self._model = model

    def render(self, ctx: RenderContext) -> str:
        resp = self._client.responses.create(
            model=self._model,
            instructions=system_prompt_for(ctx),
            input=build_user_prompt(ctx),
            max_output_tokens=900,
        )
        return resp.output_text
