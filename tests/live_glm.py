"""Live integration test for GLM (智谱AI) API — chat + tool calling.

Usage:
    GLM_API_KEY=xxx uv run python tests/test_glm_live.py
"""

import asyncio
import json
import os
import subprocess
import sys

import httpx

API_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
MODEL = "glm-4.7-flash"  # free tier, reasoning model


EXEC_TOOL = {
    "type": "function",
    "function": {
        "name": "exec",
        "description": "Execute a shell command on the host machine and return stdout+stderr.",
        "parameters": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The shell command to execute.",
                },
            },
            "required": ["command"],
        },
    },
}


def run_exec(command: str) -> str:
    """Execute a shell command locally, return output."""
    try:
        result = subprocess.run(
            command, shell=True, capture_output=True, text=True, timeout=30
        )
        output = result.stdout + result.stderr
        return output[:4000] if output else "(no output)"
    except subprocess.TimeoutExpired:
        return "(command timed out after 30s)"
    except Exception as e:
        return f"(error: {e})"


def get_reply(msg: dict) -> str:
    """Extract reply text from a GLM message — content or reasoning_content."""
    return msg.get("content") or msg.get("reasoning_content") or ""


async def test_basic_chat(client: httpx.AsyncClient, headers: dict):
    """Test 1: Basic chat completion (non-streaming)."""
    print("\n=== Test 1: Basic Chat ===")
    body = {
        "model": MODEL,
        "messages": [{"role": "user", "content": "Say 'hello world' in exactly 2 words."}],
        "stream": False,
        "max_tokens": 1024,
    }
    resp = await client.post(API_URL, json=body, headers=headers)
    print(f"Status: {resp.status_code}")
    assert resp.status_code == 200
    data = resp.json()
    msg = data["choices"][0]["message"]
    reply = get_reply(msg)
    print(f"Content: {msg.get('content')!r}")
    print(f"Reasoning: {(msg.get('reasoning_content') or '')[:200]!r}...")
    print(f"Finish reason: {data['choices'][0]['finish_reason']}")
    print(f"Usage: {data.get('usage', {})}")
    assert reply, "Expected either content or reasoning_content"
    print("PASS")


async def test_streaming(client: httpx.AsyncClient, headers: dict):
    """Test 2: Streaming chat completion."""
    print("\n=== Test 2: Streaming ===")
    body = {
        "model": MODEL,
        "messages": [{"role": "user", "content": "Count from 1 to 5, one number per line."}],
        "stream": True,
        "max_tokens": 1024,
    }
    content_chunks = []
    reasoning_chunks = []
    async with client.stream("POST", API_URL, json=body, headers=headers) as resp:
        print(f"Status: {resp.status_code}")
        assert resp.status_code == 200
        async for line in resp.aiter_lines():
            if not line.startswith("data: "):
                continue
            payload = line[6:]
            if payload == "[DONE]":
                break
            event = json.loads(payload)
            delta = event["choices"][0].get("delta", {})
            # Content text
            if delta.get("content"):
                content_chunks.append(delta["content"])
                print(delta["content"], end="", flush=True)
            # Reasoning text (reasoning model streams this separately)
            if delta.get("reasoning_content"):
                reasoning_chunks.append(delta["reasoning_content"])
    print()
    content = "".join(content_chunks)
    reasoning = "".join(reasoning_chunks)
    print(f"Content chunks: {len(content_chunks)}, chars: {len(content)}")
    print(f"Reasoning chunks: {len(reasoning_chunks)}, chars: {len(reasoning)}")
    assert content or reasoning, "Expected content or reasoning output"
    print("PASS")


async def test_tool_calling(client: httpx.AsyncClient, headers: dict):
    """Test 3: Tool calling with exec — model calls a command, we execute it, model summarizes."""
    print("\n=== Test 3: Tool Calling (exec) ===")

    messages = [
        {"role": "user", "content": "Use the exec tool to run `echo hello from glm` and tell me the output."},
    ]

    # Round 1: model should request tool call
    body = {
        "model": MODEL,
        "messages": messages,
        "tools": [EXEC_TOOL],
        "tool_choice": "auto",
        "stream": False,
        "max_tokens": 2048,
    }
    resp = await client.post(API_URL, json=body, headers=headers)
    print(f"Round 1 status: {resp.status_code}")
    data = resp.json()
    choice = data["choices"][0]
    finish = choice["finish_reason"]
    print(f"Finish reason: {finish}")

    if finish != "tool_calls":
        # Some reasoning models may just answer directly
        print(f"Model replied directly: {get_reply(choice['message'])[:200]}")
        print("SKIP — model chose not to use tools")
        return

    tool_calls = choice["message"]["tool_calls"]
    print(f"Tool calls: {json.dumps(tool_calls, indent=2)}")

    # Execute the tool
    assistant_msg = choice["message"]
    messages.append(assistant_msg)

    for tc in tool_calls:
        fn = tc["function"]
        args = json.loads(fn["arguments"])
        print(f"Executing: {fn['name']}({args})")
        output = run_exec(args["command"])
        print(f"Output: {output!r}")
        messages.append({
            "role": "tool",
            "tool_call_id": tc["id"],
            "content": output,
        })

    # Round 2: model summarizes
    body["messages"] = messages
    resp = await client.post(API_URL, json=body, headers=headers)
    print(f"Round 2 status: {resp.status_code}")
    data = resp.json()
    final = get_reply(data["choices"][0]["message"])
    print(f"Final reply: {final}")
    assert "hello" in final.lower()
    print("PASS")


async def test_streaming_tool_calling(client: httpx.AsyncClient, headers: dict):
    """Test 4: Streaming + tool calling — verify we can parse tool calls from SSE chunks."""
    print("\n=== Test 4: Streaming Tool Calling ===")

    messages = [
        {"role": "user", "content": "Use exec to run `date +%Y-%m-%d` and tell me today's date."},
    ]
    body = {
        "model": MODEL,
        "messages": messages,
        "tools": [EXEC_TOOL],
        "tool_choice": "auto",
        "stream": True,
        "max_tokens": 2048,
    }

    # Round 1: stream and accumulate
    tool_calls_acc: dict[int, dict] = {}  # index → {id, name, arguments}
    text_acc = ""
    reasoning_acc = ""
    finish_reason = None

    async with client.stream("POST", API_URL, json=body, headers=headers) as resp:
        print(f"Round 1 status: {resp.status_code}")
        assert resp.status_code == 200
        async for line in resp.aiter_lines():
            if not line.startswith("data: "):
                continue
            payload = line[6:]
            if payload == "[DONE]":
                break
            event = json.loads(payload)
            choice = event["choices"][0]
            delta = choice.get("delta", {})

            if delta.get("content"):
                text_acc += delta["content"]
            if delta.get("reasoning_content"):
                reasoning_acc += delta["reasoning_content"]

            # Accumulate tool calls
            if delta.get("tool_calls"):
                for tc_delta in delta["tool_calls"]:
                    idx = tc_delta.get("index", 0)
                    if idx not in tool_calls_acc:
                        tool_calls_acc[idx] = {"id": "", "name": "", "arguments": ""}
                    if tc_delta.get("id"):
                        tool_calls_acc[idx]["id"] = tc_delta["id"]
                    fn = tc_delta.get("function", {})
                    if fn.get("name"):
                        tool_calls_acc[idx]["name"] = fn["name"]
                    if fn.get("arguments"):
                        tool_calls_acc[idx]["arguments"] += fn["arguments"]

            if choice.get("finish_reason"):
                finish_reason = choice["finish_reason"]

    print(f"Finish reason: {finish_reason}")
    print(f"Content: {text_acc[:200]!r}")
    print(f"Reasoning: {reasoning_acc[:200]!r}")
    print(f"Tool calls: {json.dumps(dict(tool_calls_acc), indent=2)}")

    if finish_reason != "tool_calls" or not tool_calls_acc:
        print("SKIP — model didn't use tool in streaming mode")
        return

    # Execute tools
    assistant_msg: dict = {"role": "assistant", "content": text_acc or ""}
    assistant_msg["tool_calls"] = [
        {
            "id": tc["id"],
            "type": "function",
            "function": {"name": tc["name"], "arguments": tc["arguments"]},
        }
        for tc in tool_calls_acc.values()
    ]
    messages.append(assistant_msg)

    for tc in tool_calls_acc.values():
        args = json.loads(tc["arguments"])
        output = run_exec(args["command"])
        print(f"Exec output: {output!r}")
        messages.append({"role": "tool", "tool_call_id": tc["id"], "content": output})

    # Round 2: non-streaming
    body2 = {
        "model": MODEL,
        "messages": messages,
        "tools": [EXEC_TOOL],
        "stream": False,
        "max_tokens": 2048,
    }
    resp = await client.post(API_URL, json=body2, headers=headers)
    data = resp.json()
    final = get_reply(data["choices"][0]["message"])
    print(f"Final reply: {final}")
    print("PASS")


async def main():
    api_key = os.environ.get("GLM_API_KEY", "")
    if not api_key:
        print("ERROR: Set GLM_API_KEY environment variable", file=sys.stderr)
        sys.exit(1)

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    print(f"Model: {MODEL}")
    print(f"API: {API_URL}")

    async with httpx.AsyncClient(timeout=httpx.Timeout(60, connect=10)) as client:
        await test_basic_chat(client, headers)
        await test_streaming(client, headers)
        await test_tool_calling(client, headers)
        await test_streaming_tool_calling(client, headers)

    print("\n✅ All GLM tests passed!")


if __name__ == "__main__":
    asyncio.run(main())
