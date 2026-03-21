# iMessage Channel

MiniClaw 支持通过 iMessage 收发消息，使用 macOS 原生的 `imsg` CLI 工具，通过 JSON-RPC over stdio 协议通信。

## 工作原理

```
对方 iMessage → Messages.app → imsg rpc (通知) → llm.reply() → imsg rpc (send) → Messages.app → 对方
```

1. MiniClaw 启动时 spawn `imsg rpc` 子进程
2. `imsg` 监听 Messages 数据库变化，收到新消息时通过 stdout 推送 JSON-RPC notification
3. MiniClaw 收到通知后检查 allowlist，通过则处理消息：
   - Session key: `imessage:{handle}` — 每个联系人独立会话
   - 调用 `llm.reply()` 获取完整回复（非 streaming）
   - 通过同一个 RPC 连接调用 `send` 方法发送回复
4. 全程在同一进程内，无需额外 daemon 或网络端口

## 前置条件

### 系统要求

- **macOS** — iMessage 仅在 macOS 上运行
- **Messages.app 已登录** — 需要用你的 Apple ID 登录 Messages
- **imsg CLI** — 需要安装 `imsg` 工具

### 安装 imsg

```bash
brew install steipete/tap/imsg
```

验证安装：

```bash
imsg rpc --help
```

### macOS 权限

`imsg` 需要以下权限才能正常工作：

1. **Full Disk Access** — 读取 Messages 数据库（`~/Library/Messages/chat.db`）
2. **Automation 权限** — 通过 Messages.app 发送消息

首次运行时 macOS 会弹出权限请求，需要在 GUI 环境下批准。如果在无头环境运行（LaunchAgent / SSH），先在交互式终端触发权限提示：

```bash
# 触发读取权限
imsg chats --limit 1

# 触发发送权限
imsg send +14155551234 "test"
```

然后在 **系统设置 → 隐私与安全性** 中确认权限已授予。

## 配置

在 `.env` 中添加：

```bash
# 开启 iMessage 网关
IMESSAGE_ENABLED=true

# imsg 二进制路径（默认在 PATH 中查找）
IMESSAGE_CLI_PATH=imsg

# Messages 数据库路径（可选，imsg 会自动检测）
# IMESSAGE_DB_PATH=/Users/yourname/Library/Messages/chat.db

# 允许接收消息的联系人（逗号分隔，留空=接受所有人）
# IMESSAGE_ALLOW_FROM=+14155551234,friend@icloud.com

# 发送服务：auto（自动检测）、imessage（强制蓝色气泡）、sms（强制绿色气泡）
IMESSAGE_SERVICE=auto
```

### 最小配置

只需两行即可启用：

```bash
IMESSAGE_ENABLED=true
IMESSAGE_CLI_PATH=imsg
```

### 安全配置（推荐）

通过 allowlist 限制谁可以和 bot 对话：

```bash
IMESSAGE_ENABLED=true
IMESSAGE_ALLOW_FROM=+14155551234,+14155559876,friend@icloud.com
```

不在列表中的联系人发来的消息会被静默忽略。

## 使用方式

### 作为聊天通道

启动后，直接给运行 MiniClaw 的 Mac 的 iMessage 账号发消息即可。Bot 会自动回复。

```bash
python main.py
# 输出: iMessage gateway started (cli=imsg)
```

### 作为工具（主动发送）

Bot 在对话中可以使用 `imessage_send` 工具主动发送 iMessage：

```
用户：帮我给 +14155551234 发个 iMessage 说明天开会
Bot：[调用 imessage_send] → iMessage 已发送
```

支持的收件人格式：
- 手机号（E.164）：`+14155551234`
- Apple ID 邮箱：`user@icloud.com`

### Cron 任务投递

创建 cron 任务时设置 `delivery_channel: "imessage"`，`channel_id` 填收件人：

```
cron_create:
  name: "早安问候"
  schedule_type: cron
  schedule_value: "0 8 * * *"
  payload: "给我一句早安问候，用中文"
  channel_id: "+14155551234"
  delivery_channel: imessage
```

## 架构细节

### JSON-RPC 协议

MiniClaw 与 `imsg` 通过 JSON-RPC 2.0 over stdio 通信：

```
MiniClaw                    imsg rpc
   │                           │
   │── spawn ──────────────────▶│
   │                           │
   │◀── notification ──────────│  {"method":"message","params":{...}}
   │                           │
   │── request ────────────────▶│  {"jsonrpc":"2.0","id":1,"method":"send","params":{...}}
   │◀── response ──────────────│  {"jsonrpc":"2.0","id":1,"result":{...}}
```

**入站消息通知格式：**

```json
{
  "method": "message",
  "params": {
    "sender": "+14155551234",
    "text": "你好",
    "is_from_me": false,
    "chat_id": 42
  }
}
```

**发送请求格式：**

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "send",
  "params": {
    "to": "+14155551234",
    "text": "你好！有什么可以帮你的？",
    "service": "auto"
  }
}
```

### Session 管理

| 通道 | Session Key 格式 | 示例 |
|------|------------------|------|
| Discord DM | `{channel_id}:{user_id}` | `123456:789012` |
| SMS | `sms:{手机号}` | `sms:+14155551234` |
| iMessage | `imessage:{handle}` | `imessage:+14155551234` |
| iMessage | `imessage:{handle}` | `imessage:user@icloud.com` |

Handle 会被标准化：小写、去除服务前缀（`imessage:`、`sms:`）。

### 网关客户端复用

- 网关运行时，`imessage_send` 工具和 cron 投递会复用已有的 RPC 连接（避免重复 spawn 进程）
- 网关未运行时，工具会创建临时 RPC 客户端，用完即关

## 远程 Mac 部署

如果 MiniClaw 运行在另一台机器上，可以通过 SSH wrapper 连接远程 Mac 上的 `imsg`：

**1. 在远程 Mac 上安装 imsg：**

```bash
brew install steipete/tap/imsg
```

**2. 创建 SSH wrapper 脚本：**

```bash
# ~/.miniclaw/imsg-ssh.sh
#!/usr/bin/env bash
exec ssh -T bot@mac-mini.local imsg "$@"
```

```bash
chmod +x ~/.miniclaw/imsg-ssh.sh
```

**3. 配置 MiniClaw：**

```bash
IMESSAGE_ENABLED=true
IMESSAGE_CLI_PATH=~/.miniclaw/imsg-ssh.sh
```

**注意事项：**
- 确保 SSH 密钥认证已配置（无密码登录）
- 远程 Mac 的 Messages.app 需要保持登录状态
- 首次需要在远程 Mac 的 GUI 环境中批准 Full Disk Access 和 Automation 权限

## 与 SMS Channel 对比

| 特性 | SMS (Twilio) | iMessage |
|------|-------------|----------|
| 依赖 | Twilio 账号 + 号码 | macOS + imsg CLI |
| 费用 | 按条计费 | 免费 |
| 网络 | 需要公网 URL (webhook) | 无需（本地 stdio） |
| 图片 | 支持 MMS 入站 | 暂不支持 |
| 跨平台 | 任何手机 | 仅 Apple 设备 |
| 群聊 | 不支持 | 支持（通过 chat_id） |

## 故障排查

### imsg 无法启动

```bash
# 检查是否安装
which imsg

# 检查 RPC 功能
imsg rpc --help

# 手动测试 RPC
echo '{"jsonrpc":"2.0","id":1,"method":"chats.list","params":{"limit":3}}' | imsg rpc
```

### 收不到消息

1. 确认 Messages.app 已登录且可以正常收发
2. 检查 Full Disk Access 权限
3. 检查 allowlist 配置（`IMESSAGE_ALLOW_FROM`）
4. 查看日志中是否有 `blocked message from` 记录

### 发送失败

1. 确认 Automation 权限已授予
2. 手动测试发送：`imsg send +14155551234 "test"`
3. 检查收件人格式（手机号用 E.164，邮箱用完整地址）

### 权限问题（无头环境）

如果在 LaunchAgent 或 SSH 环境下运行，权限提示可能不会弹出。解决方法：

```bash
# 切换到运行 bot 的用户，在 GUI 终端中执行
imsg chats --limit 1
imsg send +14155551234 "permission test"
```

在系统设置中确认 Terminal.app（或你的终端应用）已获得 Full Disk Access。
