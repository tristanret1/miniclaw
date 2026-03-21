---
name: intern
description: "将写代码的任务委派给 Claude Code 实习生。Use when: user wants code written, bugs fixed, files edited, refactoring, tests, git operations, or any programming task."
disable-model-invocation: true
metadata:
  openclaw:
    emoji: "👨‍💻"
user-invocable: true
---

# 实习生 — Claude Code 任务委派

用户通过 `/intern` 发起编程任务时，你必须将任务委派给 Claude Code（`claude_code` 工具）来完成。

## 工作流程

1. **理解需求**：分析用户请求，明确要做什么
2. **拆分任务**：如果任务复杂，拆分为多个子任务，依次调用 `claude_code`
3. **委派执行**：调用 `claude_code` 工具，传入清晰、具体的 task 描述
4. **汇报结果**：用简洁的中文总结实习生完成了什么

## 调用 claude_code 的原则

- task 描述要具体：写明目标文件、期望行为、约束条件
- 不要笼统地说"帮我写代码"，要说"在 bot/tools.py 中新增一个 xxx 函数，参数为 yyy，返回 zzz"
- 如果用户没有指定工作目录，不要传 cwd 参数（让它使用默认值）
- 对于大型任务，分步调用比一次性塞入所有需求更可靠

## 汇报风格

- 用中文简要说明做了什么改动
- 列出修改的文件
- 如果有需要用户确认或后续操作的事项，明确提出

## 示例

用户: `/intern 给 bot/tools.py 添加一个新工具，可以查询天气`

你应该调用:
```
claude_code(task="在 bot/tools.py 中新增一个 weather 工具定义，参考现有的 EXEC_TOOL 格式。工具名为 weather，接受 city 参数（string, required），描述为查询城市天气。同时在 ALL_TOOLS 列表中注册该工具。")
```

然后汇报实习生完成的结果。
