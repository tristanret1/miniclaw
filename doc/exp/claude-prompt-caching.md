# Claude Prompt Caching 实战指南

> 基于 MiniClaw 项目的实际踩坑经验，总结 Claude API prompt caching 的工作原理、常见误区和优化策略。

---

## 1. Prompt Caching 是什么

Claude API 支持 **prompt caching**：如果连续请求的前缀（system + messages 的前半部分）相同，API 会复用上次的 KV cache，避免重新计算。

**价格对比（以 Claude Opus 4.6 为例）：**

| 计费类型 | 价格 | 相对倍率 |
|---------|------|---------|
| `input_tokens` | $15 / MTok | 1x |
| `cache_read_input_tokens` | $1.5 / MTok | **0.1x** |
| `cache_creation_input_tokens` | $18.75 / MTok | 1.25x |

缓存命中时，旧历史部分只收 1/10 的价格。**多轮对话场景下，这是最大的成本优化手段。**

---

## 2. 核心机制：cache_control 断点

Claude 不会自动缓存所有内容。你需要在请求中用 `cache_control` 标记**断点位置**，告诉 API「从开头到这里可以缓存」。

```
┌──────────────────────────────────────────────┐
│  system prompt      ← cache_control 断点 ①   │  ← 被缓存
│  tools 定义         ← cache_control 断点 ②   │  ← 被缓存
│  messages[0..N-2]   ← cache_control 断点 ③   │  ← 被缓存（旧历史）
├──────────────────────────────────────────────┤
│  messages[N-1..N]                            │  ← 每次新增，正常计费
└──────────────────────────────────────────────┘
```

**规则：**
- 最多 4 个 `cache_control` 断点
- 缓存从请求开头精确匹配到最后一个断点位置
- 断点后面的内容变化不影响缓存命中
- TTL 为 **5 分钟**（ephemeral 类型），超时后需重建

---

## 3. 我们踩过的坑

### 3.1 只在 system 上加断点 → 缓存几乎无用

**错误写法：**

```python
def _build_body(self, messages, system, tools, max_tokens, stream):
    body = {
        "model": self.model,
        "system": [
            {"type": "text", "text": system, "cache_control": {"type": "ephemeral"}},
        ],
        "messages": messages,   # ← 没有任何 cache_control
        "tools": tools,         # ← 也没有
    }
    return body
```

**结果：** 每次请求只有 system prompt（~6800 tokens）被缓存，但由于 system 之后的 messages 每次都变，缓存经常失效。

实际日志（注意 `cache_read=0`）：

```
messages=11: input=6238,  cache_read=0, cache_create=6831
messages=13: input=7250,  cache_read=0, cache_create=6831  ← 重新创建
messages=15: input=8285,  cache_read=0, cache_create=6831  ← 又重新创建
messages=17: input=9186,  cache_read=0, cache_create=6831  ← 又重新创建
messages=39: input=13973, cache_read=0, cache_create=6831  ← 持续到最后
```

15 轮对话总共消费了约 160k input tokens，全额计费。

### 3.2 图片 base64 破坏缓存前缀

截图的 base64 编码每次像素级不同，即使是同一个页面。如果截图存在历史消息中：

```
messages[0]: user "打开 twitter"
messages[1]: assistant tool_use(browser, navigate)
messages[2]: user tool_result [text_info, IMAGE_BASE64_AAA...]   ← 第一次截图
messages[3]: assistant "页面加载完成"
messages[4]: user "点击搜索"
messages[5]: assistant tool_use(browser, click)
messages[6]: user tool_result [text_info, IMAGE_BASE64_BBB...]   ← 第二次截图（不同的 base64）
```

每次截图的 base64 都不同 → messages 前缀从 `messages[2]` 开始就不匹配 → **cache miss**。

**解决方案：** 截图只在当前 API 调用中保留（内存），存入 DB 时替换为文本占位符。

```python
# processor.py — 双版本 tool_result 策略
tool_results, tool_results_for_history = await self._handle_tool_calls(tool_blocks)

# 纯文本版本写入 DB（保持前缀稳定）
await self.session.append(self.session_key, "user", tool_results_for_history)

if tool_results != tool_results_for_history:
    # 内存中用完整版本（含截图），让当前工具循环的 LLM 能看到图片
    history[-1] = {"role": "user", "content": tool_results}
```

构建纯文本版本的逻辑：

```python
# 将 image block 替换为文本占位符
for r in full_results:
    content = r.get("content")
    if isinstance(content, list) and any(
        isinstance(b, dict) and b.get("type") == "image" for b in content
    ):
        text_parts = [
            b.get("text", "") for b in content
            if isinstance(b, dict) and b.get("type") == "text"
        ]
        history_results.append({
            **r,
            "content": "\n".join(text_parts) + "\n[screenshot taken]",
        })
    else:
        history_results.append(r)
```

### 3.3 图片的 token 消耗：base64 vs URL 没有区别

Claude 计算图片 token 基于**像素尺寸**，不是传输方式。base64 和 URL 最终都会被解码成同样的图片。

| 方式 | Token 消耗 |
|------|-----------|
| 1280x720 截图（base64） | ~1,600 tokens |
| 1280x720 截图（URL） | ~1,600 tokens |
| 结构化文本提取 | ~1,000-3,000 tokens |

**真正省 token 的方式是不发图片** — 用结构化文本替代。

---

## 4. 正确的缓存策略

### 4.1 在 messages 中注入断点

关键：在**倒数第二个 user turn** 上打断点。这样旧历史被缓存，每轮只有最新消息计费。

```python
@staticmethod
def _inject_cache_breakpoints(messages: list[Message]) -> list[Message]:
    """在 messages 中注入 cache_control 断点。

    策略：在倒数第二个 user turn 上打断点。
    system(断点①) + tools(断点②) + 旧历史(断点③) 全部被缓存，
    每轮只有最新一轮对话需要正常计费。
    """
    if not messages:
        return messages

    user_indices = [i for i, m in enumerate(messages) if m.get("role") == "user"]

    if len(user_indices) < 2:
        return messages  # 只有一轮，没有旧历史可缓存

    messages = list(messages)  # 浅拷贝，不污染 session cache
    target_idx = user_indices[-2]
    msg = dict(messages[target_idx])
    content = msg.get("content")

    if isinstance(content, str):
        # 纯文本 → 转为 text block + cache_control
        msg["content"] = [{
            "type": "text",
            "text": content,
            "cache_control": {"type": "ephemeral"},
        }]
    elif isinstance(content, list):
        # block 列表 → 在最后一个 block 上加 cache_control
        content = [dict(b) if isinstance(b, dict) else b for b in content]
        for i in range(len(content) - 1, -1, -1):
            if isinstance(content[i], dict):
                content[i] = {**content[i], "cache_control": {"type": "ephemeral"}}
                break
        msg["content"] = content

    messages[target_idx] = msg
    return messages
```

### 4.2 在 tools 上也加断点

Tool 定义在整个会话中不变，非常适合缓存：

```python
def _build_body(self, messages, system, tools, max_tokens, stream):
    cached_messages = self._inject_cache_breakpoints(messages)
    body = {
        "model": self.model,
        "max_tokens": max_tokens,
        "system": self._build_system_blocks(system),   # 断点 ① ②
        "messages": cached_messages,                     # 断点 ③
        "stream": stream,
    }
    if tools:
        tools = list(tools)
        # 在最后一个 tool 上打断点 — tool 定义不变，适合缓存
        tools[-1] = {**tools[-1], "cache_control": {"type": "ephemeral"}}
        body["tools"] = tools
    return body
```

### 4.3 断点分配总览

| 断点 | 位置 | 内容 | 变化频率 |
|-----|------|------|---------|
| ① | system block 1 | Claude Code prefix | 永不变 |
| ② | system block 2 | bot system prompt | 每次启动时可能变 |
| ③ | tools[-1] | 工具定义 | 永不变 |
| ④ | messages 倒数第二个 user turn | 旧对话历史 | 每轮滚动 |

---

## 5. 优化效果对比

### 修复前

```
messages=11: input=6238,  cache_read=0,    cache_create=6831
messages=13: input=7250,  cache_read=0,    cache_create=6831
messages=15: input=8285,  cache_read=0,    cache_create=6831
messages=25: input=10588, cache_read=6831, cache_create=0     ← 偶尔命中
messages=27: input=11524, cache_read=0,    cache_create=6831  ← 又丢了
```

15 轮总计：~160k input tokens，全额计费。

### 修复后（预期）

```
messages=11: input=6238,  cache_read=0,    cache_create=6831   ← 首次创建
messages=13: input=~1000, cache_read=6831, cache_create=~400   ← 命中！
messages=15: input=~1000, cache_read=7200, cache_create=~400   ← 继续命中
messages=25: input=~1000, cache_read=9500, cache_create=~400   ← 持续命中
```

15 轮总计：~15k input + ~130k cache_read。按价格算省 **70-80%**。

---

## 6. 额外优化：压缩旧 tool_result

多轮工具调用（如连续搜索）会让 tool_result 快速堆积。即使有缓存，膨胀的历史仍然增加 cache_creation 成本和延迟。

**策略：** 当历史超过阈值时，将旧 tool_result 内容替换为占位符，只保留最近一轮的完整结果。

```python
_COMPACT_CHAR_THRESHOLD = 40_000  # ~10k tokens

def _compact_tool_results(history: list[dict]) -> None:
    """原地压缩历史中的旧 tool_result。"""
    if _estimate_history_chars(history) < _COMPACT_CHAR_THRESHOLD:
        return

    # 找所有含 tool_result 的 user 消息
    tool_msg_indices = [
        i for i, msg in enumerate(history)
        if msg.get("role") == "user"
        and isinstance(msg.get("content"), list)
        and any(isinstance(b, dict) and b.get("type") == "tool_result" for b in msg["content"])
    ]

    if len(tool_msg_indices) <= 1:
        return

    # 保留最后一条，压缩其余
    for idx in tool_msg_indices[:-1]:
        content = history[idx]["content"]
        compacted = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "tool_result":
                compacted.append({
                    "type": "tool_result",
                    "tool_use_id": block.get("tool_use_id", ""),
                    "content": "[已清理的工具结果]",
                })
            else:
                compacted.append(block)
        history[idx] = {"role": "user", "content": compacted}
```

实测效果：6 轮搜索（每轮 3 个工具调用），54k chars → 9k chars，压缩 83%。

---

## 7. 检查清单

在你的 Claude API 集成中，逐项确认：

- [ ] system prompt 上有 `cache_control` 断点
- [ ] tools 定义上有 `cache_control` 断点
- [ ] messages 中在倒数第二个 user turn 上注入 `cache_control` 断点
- [ ] 不修改原始 session 数据（拷贝后操作）
- [ ] 截图 / 图片不存入历史记录（用文本占位符替代）
- [ ] 长历史中的旧 tool_result 有压缩机制
- [ ] 日志中打印 `cache_read` / `cache_create` 用于监控
- [ ] 对话间隔尽量在 5 分钟内（ephemeral TTL）

---

## 8. 参考

- [Anthropic Prompt Caching 文档](https://docs.anthropic.com/en/docs/build-with-claude/prompt-caching)
- 本项目实现：`bot/provider/anthropic.py` — `_inject_cache_breakpoints()`、`_build_system_blocks()`
- 图片剥离：`bot/processor.py` — `_handle_tool_calls()` 双版本策略
- 历史压缩：`bot/processor.py` — `_compact_tool_results()`
