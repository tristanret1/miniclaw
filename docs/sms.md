# SMS Channel

MiniClaw 支持通过 Twilio 接收和回复短信，与 Discord 并行运行在同一进程中。

## 工作原理

```
用户手机 → Twilio → POST /sms (aiohttp webhook) → llm.reply() → run_sms() → Twilio → 用户手机
```

1. 用户发短信到你的 Twilio 号码
2. Twilio 将消息 POST 到你配置的 webhook URL
3. Webhook 立即返回空 `<Response/>`（避免 Twilio 15s 超时重试）
4. 后台 `asyncio.create_task` 处理消息：
   - Session key: `sms:{手机号}` — 每个号码独立会话
   - 调用 `llm.reply()` 获取完整回复（非 streaming）
   - 通过 `run_sms()` 发送回复短信
5. 支持 MMS 图片（自动提取 `MediaUrl` 传给 LLM）

## 配置

在 `.env` 中添加：

```bash
# 开启 SMS 网关
SMS_ENABLED=true
SMS_WEBHOOK_PORT=8080

# 公网 URL（用于 Twilio 签名验证）
SMS_WEBHOOK_URL=https://your-domain.ngrok.io/sms

# Twilio 凭证（发短信 + 签名验证都需要）
TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TWILIO_AUTH_TOKEN=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TWILIO_FROM_NUMBER=+14155551234
```

## Twilio 配置

1. 登录 [Twilio Console](https://console.twilio.com)
2. 进入 Phone Numbers → 你的号码 → Messaging Configuration
3. 设置 "A message comes in" webhook 为 `https://your-domain/sms`（POST）

## 本地开发

用 ngrok 暴露本地端口：

```bash
ngrok http 8080
```

将 ngrok 给的 URL（如 `https://abc123.ngrok.io/sms`）填入：
- `.env` 的 `SMS_WEBHOOK_URL`
- Twilio Console 的 webhook URL

## Cron 任务通过 SMS 投递

创建 cron 任务时设置 `delivery_channel: "sms"`，`channel_id` 填手机号（E.164 格式）：

```
cron_create:
  name: "早安问候"
  schedule_type: cron
  schedule_value: "0 8 * * *"
  payload: "给我一句早安问候"
  channel_id: "+14155551234"
  delivery_channel: sms
```

## 安全

- **签名验证**：配置了 `TWILIO_AUTH_TOKEN` 后，所有请求会验证 `X-Twilio-Signature`（HMAC-SHA1），拒绝伪造请求
- 未配置 auth token 时签名验证跳过（仅限开发环境）
