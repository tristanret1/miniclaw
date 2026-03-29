# Pixel Town

Stardew Valley 风格的像素小镇 UI，用于可视化 MiniClaw agent 的实时状态。浏览器端使用 PixiJS + TypeScript，后端通过 aiohttp 提供 WebSocket 和 REST API。

## 快速开始

### 前端（开发模式）

```bash
cd pixeltown
npm install
npm run dev          # Vite 开发服务器，默认 http://localhost:5173
```

打开浏览器即可看到 Demo 模式（3 个演示 Agent：Claude、Codex、Ralph）。无需后端也可运行。

### 前端（生产构建）

```bash
cd pixeltown
npm run build        # 输出到 pixeltown/dist/
```

### 后端

后端是 aiohttp 服务器，嵌入 MiniClaw 主进程运行：

```python
from src.status import AgentStatusTracker
from src.gateway_pixeltown import PixelTownGateway

tracker = AgentStatusTracker(["agent-1", "agent-2", "agent-3"])
gateway = PixelTownGateway(tracker, port=8765)
await gateway.start()
```

启动后访问 `http://127.0.0.1:8765`，前端 dev server 会自动代理 `/api` 和 `/ws` 到后端。

### 测试

```bash
# TypeScript 类型检查
cd pixeltown && npx tsc --noEmit

# Python 测试
pytest tests/ -v
```

---

## 功能说明

### 小镇场景

- **Agent 小屋** — 每个 Agent 一栋，烟囱冒烟表示正在工作，窗户亮灯表示在线
- **中央广场** — 公告栏（点击打开 Dashboard），空闲 Agent 在此闲逛
- **图书馆** — Agent 工作时走向这里
- **商店** — V1 装饰性建筑

### Agent 状态机

| 状态 | 触发条件 | 视觉效果 |
|------|---------|---------|
| IDLE | 无任务 | 随机漫步、坐长椅、看花 |
| WORKING | 处理消息/Cron 任务 | 走向图书馆，头顶 ⚡ |
| SLEEPING | 超过 23:00 | 回小屋，头顶 💤 |
| SOCIALIZING | 两个空闲 Agent 靠近 | 面对面，头顶 💬 |
| OFFLINE | 进程未运行 | 半透明灰色 |

### 交互操作

| 操作 | 目标 | 效果 |
|------|------|------|
| 单击 | Agent | 弹出状态气泡（名称、状态、详情） |
| 双击 | Agent | 打开消息输入框，发送消息 |
| 点击 | 小屋 | 进入室内视图（家具、状态面板、操作按钮） |
| 点击 | 广场 | 打开 Dashboard（全局状态概览） |
| 拖拽 | 建筑（编辑模式） | 重新排列建筑位置 |

### 环境系统

- **昼夜循环** — 同步系统时间，日出(6-8h)、白天(8-17h)、日落(17-19h)、夜晚(19-6h)，通过 ColorMatrixFilter 实现
- **天气系统** — 晴天（飞鸟）、雨天（雨滴+蓝灰滤镜）、雪天（雪花）、雷暴（暴雨+闪电），每 1-4 小时随机切换
- **季节系统** — 同步日历月份，春（樱花飘落）、夏（浓绿）、秋（落叶）、冬（冷色调）

### 侧边栏

- **Agent 列表** — 彩色状态点 + 当前状态
- **定时任务** — Cron 任务列表，一键触发
- **活动日志** — 最近 20 条事件
- **设置** — 音效开关、编辑布局模式
- **时钟** — 当前时间 + 季节图标

### 室内视图

点击 Agent 小屋进入：
- 像素风家具（床、书桌、书架、盆栽）
- 底部状态栏：状态、详情、操作按钮
- **Message** — 向 Agent 发消息
- **Pause/Resume** — 暂停/恢复 Agent
- **< Back** — 返回小镇

---

## API

### REST

| Method | Path | 说明 |
|--------|------|------|
| GET | `/api/agents` | Agent 列表 + 状态 |
| GET | `/api/agents/:id` | 单个 Agent 详情 |
| POST | `/api/agents/:id/message` | 发送消息 `{"text": "..."}` |
| POST | `/api/agents/:id/trigger` | 触发任务 `{"job_id": "..."}` |
| GET | `/api/cron` | Cron 任务列表 |
| GET | `/api/weather` | 天气状态 |
| PUT | `/api/town/layout` | 保存布局 `{"buildings": [...]}` |

### WebSocket (`/ws`)

连接后服务端推送 `init` 消息（完整状态），之后实时推送：
- `agent_status` — Agent 状态变化
- `social_event` — 社交互动
- `cron_event` — 任务开始/结束
- `message_received` — 新消息通知

客户端可发送：
- `send_message` — 发消息给 Agent
- `trigger_task` — 触发 Cron 任务
- `toggle_agent` — 启用/停用 Agent
- `save_layout` — 保存建筑布局

---

## 项目结构

```
pixeltown-design/
├── pixeltown/                    # 前端 (Vite + PixiJS + TypeScript)
│   ├── src/
│   │   ├── main.ts              # 入口：初始化 PixiJS、场景管理、组件接线
│   │   ├── config.ts            # 常量：瓦片大小、颜色、行为权重
│   │   ├── scenes/
│   │   │   ├── TownScene.ts     # 主场景：地图、建筑、Agent、系统集成
│   │   │   └── HouseScene.ts    # 室内场景：家具、状态面板、操作按钮
│   │   ├── entities/
│   │   │   ├── Agent.ts         # Agent 精灵：状态机、寻路移动
│   │   │   └── Building.ts      # 建筑精灵：小屋、图书馆、商店、广场
│   │   ├── systems/
│   │   │   ├── DayNight.ts      # 昼夜循环
│   │   │   ├── Weather.ts       # 天气：粒子效果 + 滤镜
│   │   │   ├── Season.ts        # 季节：色调 + 粒子
│   │   │   ├── Pathfinding.ts   # A* 寻路
│   │   │   ├── IdleBehavior.ts  # 空闲行为树
│   │   │   └── SocialAI.ts      # 社交互动（亲密度驱动）
│   │   ├── ui/
│   │   │   ├── UIOverlay.ts     # 侧边栏：Agent 列表、Cron、设置、时钟
│   │   │   ├── StatusBubble.ts  # 点击 Agent 弹出状态气泡
│   │   │   ├── MessageInput.ts  # 消息输入框
│   │   │   ├── Dashboard.ts     # 公告栏全局面板
│   │   │   └── LayoutEditor.ts  # 拖拽编辑建筑布局
│   │   └── net/
│   │       ├── Protocol.ts      # WebSocket 消息类型定义
│   │       └── WebSocketClient.ts # WS 连接 + 自动重连
│   └── index.html
├── src/                          # 后端 (Python aiohttp)
│   ├── status.py                # AgentStatusTracker：状态聚合 + 亲密度计算
│   └── gateway_pixeltown.py     # WebSocket + REST API 网关
└── tests/
    ├── test_status.py           # 状态追踪器测试 (14 tests)
    └── test_gateway.py          # 网关测试 (7 tests)
```

---

## 配置

在 MiniClaw 的 `config.yaml` 中添加：

```yaml
gateway:
  pixeltown:
    enabled: true
    port: 8765
    host: "127.0.0.1"
    static_dir: "pixeltown/dist"
    layout_file: "workspace/town_layout.json"
    idle_behavior:
      wander_interval: [10, 30]
      social_chance: 0.3
      sleep_after: "23:00"
```
