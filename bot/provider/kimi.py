"""Kimi provider — Moonshot AI (月之暗面) chat completions with tool calling."""

from bot.provider.openai_compat import OpenAICompatProvider


class KimiProvider(OpenAICompatProvider):
    ENV_KEY = "KIMI_API_KEY"

    def __init__(self, model: str):
        super().__init__(model)
        from bot.config import get_config
        self.API_URL = get_config().llm.kimi.api_url
