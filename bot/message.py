"""Unified message types for LLM communication."""

from typing import Literal, TypedDict, Union

Role = Literal["user", "assistant"]


class TextBlock(TypedDict):
    type: Literal["text"]
    text: str


class ImageBlock(TypedDict):
    type: Literal["image"]
    source: dict  # {type: "url", url: str} or {type: "base64", ...}


class ToolUseBlock(TypedDict):
    type: Literal["tool_use"]
    id: str
    name: str
    input: dict


class ToolResultBlock(TypedDict):
    type: Literal["tool_result"]
    tool_use_id: str
    content: str


ContentBlock = Union[TextBlock, ImageBlock, ToolUseBlock, ToolResultBlock]
Content = Union[str, list[ContentBlock]]


class Message(TypedDict):
    role: Role
    content: Content


def build_user_content(text: str, image_urls: list[str] | None = None) -> Content:
    """Build user message content, optionally with images."""
    if not image_urls:
        return text

    blocks: list[ContentBlock] = []
    for url in image_urls:
        blocks.append({
            "type": "image",
            "source": {"type": "url", "url": url},
        })
    if text:
        blocks.append({"type": "text", "text": text})
    return blocks


def extract_text(content: Content) -> str:
    """Extract plain text from Content."""
    if isinstance(content, str):
        return content
    return "\n".join(
        block["text"] for block in content
        if isinstance(block, dict) and block.get("type") == "text"
    )
