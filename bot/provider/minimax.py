"""MiniMax provider — MiniMax chat completions with tool calling."""

from bot.message import Message
from bot.provider.openai_compat import OpenAICompatProvider


class MinimaxProvider(OpenAICompatProvider):
    ENV_KEY = "MINIMAX_API_KEY"

    def __init__(self, model: str):
        super().__init__(model)
        from bot.config import get_config
        self.API_URL = get_config().llm.minimax.api_url

    def _build_body(
        self,
        messages: list[Message],
        system: str,
        tools: list[dict] | None,
        max_tokens: int,
        stream: bool,
    ) -> dict:
        """MiniMax uses max_completion_tokens instead of max_tokens."""
        body = super()._build_body(messages, system, tools, max_tokens, stream)
        body.pop("max_tokens", None)
        body["max_completion_tokens"] = max_tokens
        return body
