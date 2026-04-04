"""GLM provider — 智谱AI (Zhipu AI) chat completions with tool calling."""

from bot.provider.openai_compat import OpenAICompatProvider


class GLMProvider(OpenAICompatProvider):
    ENV_KEY = "GLM_API_KEY"

    def __init__(self, model: str):
        super().__init__(model)
        from bot.config import get_config
        self.API_URL = get_config().llm.glm.api_url
