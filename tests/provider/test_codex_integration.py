"""Integration tests — real Codex API calls.

Run with: pytest tests/provider/test_codex_integration.py -v -s
Requires: .codex_credentials.json with valid tokens.
"""

import pytest
from bot.oauth.codex import load_credentials
from bot.provider.codex import CodexProvider

# Skip all tests if no credentials
pytestmark = pytest.mark.skipif(
    not load_credentials(),
    reason="No .codex_credentials.json — skipping Codex integration tests",
)

MODEL = "gpt-5.3-codex"


@pytest.fixture
def provider():
    return CodexProvider(model=MODEL)


class TestCodexIntegration:
    async def test_simple_text(self, provider):
        """Send a simple message, get a text reply."""
        messages = [{"role": "user", "content": "Say hello in exactly 3 words."}]
        response = await provider.call(messages, system="You are a helpful assistant.")
        print(f"\n[call] response: {response}")

        assert "content" in response
        assert len(response["content"]) > 0
        assert response["content"][0]["type"] == "text"
        assert len(response["content"][0]["text"]) > 0
        assert response["stop_reason"] == "end_turn"

    async def test_streaming(self, provider):
        """Stream a response, collect text chunks."""
        messages = [{"role": "user", "content": "Count from 1 to 5, one number per line."}]
        chunks = []
        async for event in provider.stream(messages, system="You are a helpful assistant."):
            etype = event.get("_event")
            if etype == "content_block_delta":
                delta = event.get("delta", {})
                if delta.get("type") == "text_delta":
                    chunks.append(delta["text"])

        text = "".join(chunks)
        print(f"\n[stream] collected: {text!r}")
        assert len(text) > 0
        assert "1" in text

    async def test_tool_use(self, provider):
        """Verify Codex calls a function tool when asked."""
        tools = [{
            "name": "get_weather",
            "description": "Get the current weather for a city.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "city": {"type": "string", "description": "City name"},
                },
                "required": ["city"],
            },
        }]
        messages = [{"role": "user", "content": "What's the weather in Tokyo?"}]

        response = await provider.call(
            messages,
            system="Use the get_weather tool to answer weather questions.",
            tools=tools,
        )
        print(f"\n[tool_use] response: {response}")

        assert response["stop_reason"] == "tool_use"
        tool_blocks = [b for b in response["content"] if b["type"] == "tool_use"]
        assert len(tool_blocks) >= 1
        assert tool_blocks[0]["name"] == "get_weather"
        assert "city" in tool_blocks[0]["input"]

    async def test_tool_use_streaming(self, provider):
        """Stream a tool_use response, verify events translate correctly."""
        tools = [{
            "name": "exec",
            "description": "Execute a shell command.",
            "input_schema": {
                "type": "object",
                "properties": {"command": {"type": "string"}},
                "required": ["command"],
            },
        }]
        messages = [{"role": "user", "content": "Run the command: echo hello"}]

        events = []
        async for event in provider.stream(
            messages,
            system="Always use the exec tool to run commands.",
            tools=tools,
        ):
            events.append(event)
            etype = event.get("_event")
            print(f"  event: {etype} → {event}")

        # Should have content_block_start for tool_use
        etypes = [e.get("_event") for e in events]
        assert "content_block_start" in etypes
        assert "message_delta" in etypes

        # Final message_delta should have stop_reason
        final = [e for e in events if e.get("_event") == "message_delta"]
        assert final[-1]["delta"]["stop_reason"] in ("tool_use", "end_turn")

    async def test_multi_turn(self, provider):
        """Multi-turn conversation works correctly."""
        messages = [
            {"role": "user", "content": "My name is TestBot."},
            {"role": "assistant", "content": [{"type": "text", "text": "Nice to meet you, TestBot!"}]},
            {"role": "user", "content": "What is my name?"},
        ]
        response = await provider.call(messages, system="")
        text = response["content"][0]["text"].lower()
        print(f"\n[multi-turn] reply: {text}")
        assert "testbot" in text
