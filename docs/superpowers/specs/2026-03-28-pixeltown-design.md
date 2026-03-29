# MiniClaw Pixel Town — Design Spec

A pixel-art virtual town UI for MiniClaw agents. Stardew Valley-inspired, browser-based, real-time status visualization with full interaction capabilities.

---

## 1. Overview

Pixel Town is a browser-based pixel-art town where each MiniClaw agent has a cottage and a virtual presence. Users open a local web page to see agents walking around, working, socializing, or sleeping — all driven by real-time data from MiniClaw's runtime. Users can also interact: send messages, trigger tasks, and toggle agents directly from the UI.

**Tech stack:**
- Frontend: PixiJS + TypeScript + Vite
- Communication: WebSocket (bidirectional real-time)
- Backend: aiohttp server embedded in MiniClaw (new gateway)
- Map editor: Tiled Map Editor → JSON export
- Assets: Free pixel art packs from itch.io (CC0/free license)

---

## 2. System Architecture

### New Modules

| Module | Role |
|--------|------|
| `bot/gateway/pixeltown.py` | aiohttp web server: static files + WebSocket + REST API |
| `bot/status.py` | Agent status tracker: aggregates events, computes social affinity |
| `pixeltown/` | Frontend project (Vite + TypeScript + PixiJS) |

### Integration Pattern

Same pattern as the existing SMS gateway (`bot/gateway/sms.py`): launched as an additional async task from `main.py`, configured in `config.yaml` under `gateway.pixeltown`.

### Data Flow

```
MiniClaw Runtime (Discord, Cron, Gateways)
        │
        ▼
  bot/status.py — AgentStatusTracker
  • Listens to: client.py (messages), cron.py (jobs), gateway/* (activity)
  • Aggregates state: working / idle / sleeping / offline
  • Computes social affinity from sessions.db interaction overlap
        │
        ▼
  bot/gateway/pixeltown.py — WebSocket Gateway
  • Pushes state changes to connected browsers
  • Receives user commands (send message, trigger task, toggle agent)
  • Serves pixeltown/dist/ as static files
  • REST API for initial data load
        │
        ▼
  Browser (PixiJS)
  • Renders tile map, agent sprites, environment effects
  • Client-side: pathfinding, idle behavior simulation, animations
  • HTML overlay: sidebar, status bubbles, message input, dashboard
```

### REST API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/agents` | Agent list with current status |
| GET | `/api/agents/:id` | Single agent details (status, stats, recent memory) |
| GET | `/api/cron` | Cron job list |
| POST | `/api/agents/:id/message` | Send message to agent |
| POST | `/api/agents/:id/trigger` | Trigger a cron task |
| PUT | `/api/town/layout` | Save town layout |
| GET | `/api/weather` | Current weather state |

---

## 3. Town Scene Design

### Layout

Stardew Valley-style top-down pixel town. Tile size: 16×16 pixels (or 32×32 for higher detail — decided when selecting asset pack). The map is authored in Tiled Map Editor and exported as JSON for PixiJS to load.

**Areas:**

- **Agent Cottages** — One per agent, personalized by IDENTITY.md (emoji, color, decorations). Mailbox at the door shows unread message count. Chimney smokes when agent is working. Click to enter interior view.
- **Central Plaza** — Public social area with fountain, benches, flower beds, bulletin board. Idle agents wander here. Bulletin board shows global status summary (active agents, today's task count). Two agents "chat" by sitting on a bench together.
- **Library** — Where agents go when working. Sitting at a desk with typing animation, ⚡ bubble overhead. Windows glow when occupied.
- **Shop** — Reserved for future features (skill shop, tool upgrades, agent customization). Decorative building in V1.

### Customizable Layout

Users can rearrange buildings via a drag-and-drop layout editor (edit mode). Layout is persisted to `workspace/town_layout.json`.

---

## 4. Agent Character System

### State Machine

| State | Trigger | Visual |
|-------|---------|--------|
| **IDLE** | No active tasks, within active hours | Random wandering, sitting on bench, looking at flowers, returning to cottage |
| **WORKING** | Processing message, running cron job, gateway activity | Walks to library, sits at desk, typing animation, ⚡ bubble |
| **SLEEPING** | Past `sleep_after` time (configurable, default 23:00) | Returns to cottage, lights off, 💤 bubble floats from window |
| **SOCIALIZING** | Two idle agents come near each other | Face-to-face, 💬 speech bubbles alternate |
| **OFFLINE** | Agent process not running | Semi-transparent + grayscale sprite, motionless |

State transitions are driven by real-time data from `bot/status.py`. Idle behavior (wandering, visiting) is simulated client-side.

### Data-Driven Social System

**Affinity scoring:**
- Source: `sessions.db` — frequency of two agents being mentioned by the same user within a time window
- Effect: Higher affinity → more frequent visits between cottages, longer chat duration at plaza
- Visual: Speech bubble color warms from white → pink → red with higher affinity
- Decay: Affinity decreases over time without shared interactions

**Idle behavior tree:**
1. Pick random action: wander (40%), visit cottage (20%), sit on bench (15%), look at flowers (10%), go to plaza (15%)
2. If another idle agent is nearby, roll social_chance (default 0.3) → trigger SOCIALIZING
3. Execute action with A* pathfinding to target tile
4. Wait random interval (configurable: 10-30s default), repeat

---

## 5. Environment Systems

### Day/Night Cycle

Synchronized to real system time (local timezone).

| Time | Phase | Effect |
|------|-------|--------|
| 06:00-08:00 | Sunrise | Warm orange filter fading out |
| 08:00-17:00 | Daytime | Normal brightness |
| 17:00-19:00 | Sunset | Warm gold → dark purple transition |
| 19:00-06:00 | Night | Deep blue filter, stars twinkle overlay |

Implementation: PixiJS `ColorMatrixFilter` on the root container. Night adds: cottage window glow (for online agents), street lamps on, star particle layer.

### Weather System

Four weather types with particle effects and global filters:

| Weather | Particles | Filter | Agent behavior |
|---------|-----------|--------|----------------|
| ☀️ Sunny | Birds flying | Normal | Default |
| 🌧 Rainy | Rain droplets | Blue-gray tint | Agents carry umbrellas |
| ❄️ Snowy | Snowflakes | White overlay, ground snow | Snow accumulation tiles |
| ⛈ Thunderstorm | Rain + lightning flash | Dark filter + screen flash | Agents run back to cottages |

**Data source (configurable):**
- `simulated` (default): Random weather weighted by season, transitions every 1-4 hours
- `real`: OpenWeatherMap free API, synced to user's location

### Season System

Synchronized to real calendar months.

| Season | Months | Tile changes |
|--------|--------|-------------|
| 🌸 Spring | Mar-May | Blooming flowers, light green grass, cherry blossom particles |
| ☀️ Summer | Jun-Aug | Deep green canopy, vibrant colors |
| 🍂 Autumn | Sep-Nov | Orange/red leaves, falling leaf particles, pumpkin decorations |
| ❄️ Winter | Dec-Feb | Snow-covered ground, bare trees, heavier chimney smoke |

Implementation: Each season has a variant tile set. Season change swaps the tilemap texture layer.

---

## 6. Interior View

Clicking a cottage transitions to an interior scene showing the agent's room with pixel furniture (bed, desk, bookshelf, potted plant, wall art).

**Status panel at bottom:**
- Current status with detail text (e.g., "🟢 Working — Replying to Discord #general")
- Today's task stats: completed / in-progress / pending
- Latest memory entry
- Runtime duration, message count, closest affinity partner

**Action buttons:**
- 💬 Send Message — opens text input, sends via WebSocket
- ⚡ Trigger Task — dropdown of available cron jobs for this agent
- ⏸ Pause/Resume Agent — toggle agent enabled state

---

## 7. UI Overlay

HTML/CSS overlay on top of the PixiJS canvas (not rendered in Canvas — keeps text crisp and accessible).

### Sidebar (collapsible)

- **Agent List** — All agents with status indicator (colored dot + status text)
- **Activity Log** — Recent agent activity stream (messages received/sent, tasks started/completed)
- **Cron Tasks** — List of scheduled jobs with next run time, trigger button
- **Settings** — Weather mode toggle, layout edit mode, sound on/off
- **Clock** — Current time + season indicator

### On-Map Interactions

| Action | Target | Result |
|--------|--------|--------|
| Click | Agent sprite | Status bubble popup (name, status, brief info) |
| Double-click | Agent sprite | Message input box opens |
| Click | Cottage | Enter interior view |
| Click | Bulletin board | Global dashboard overlay |
| Drag | Building (edit mode) | Reposition building, save layout |

---

## 8. Frontend Project Structure

```
pixeltown/
├── index.html
├── vite.config.ts
├── package.json
├── tsconfig.json
│
├── src/
│   ├── main.ts                 # Init PixiJS App + WebSocket
│   ├── config.ts               # Constants: tile size, frame rate, color maps
│   │
│   ├── scenes/
│   │   ├── TownScene.ts        # Main scene: tilemap + agent management
│   │   └── HouseScene.ts       # Cottage interior scene
│   │
│   ├── entities/
│   │   ├── Agent.ts            # Agent sprite: state machine, animations, pathfinding movement
│   │   ├── Building.ts         # Building sprite: cottage, library, shop
│   │   └── NPC.ts              # Reusable character base class
│   │
│   ├── systems/
│   │   ├── DayNight.ts         # Day/night cycle: time → filter mapping
│   │   ├── Weather.ts          # Weather: particles + filters
│   │   ├── Season.ts           # Season: tile set swap
│   │   ├── Pathfinding.ts      # A* on tile collision layer
│   │   ├── SocialAI.ts         # Social decision-making (affinity-driven)
│   │   └── IdleBehavior.ts     # Idle behavior tree (wander, sit, visit)
│   │
│   ├── ui/
│   │   ├── Sidebar.ts          # Collapsible sidebar (HTML overlay)
│   │   ├── StatusBubble.ts     # Click-agent popup
│   │   ├── MessageInput.ts     # Send message input box
│   │   ├── Dashboard.ts        # Bulletin board global dashboard
│   │   └── LayoutEditor.ts     # Drag-and-drop building editor
│   │
│   ├── net/
│   │   ├── WebSocketClient.ts  # WS connection + auto-reconnect
│   │   └── Protocol.ts         # Message type definitions (shared types)
│   │
│   └── assets/
│       ├── sprites/            # Character sprite sheets (4-dir walk, sit, sleep)
│       ├── tiles/              # Tile sets (with seasonal variants)
│       ├── ui/                 # UI icons, panels, dialog frames
│       └── maps/               # Tiled JSON map exports
│
└── public/
    └── favicon.ico
```

---

## 9. Backend Additions

### bot/status.py — AgentStatusTracker

```python
class AgentStatusTracker:
    """Aggregates agent activity events into status states."""

    # Event sources:
    #   client.py → on_message processing start/end
    #   cron.py   → job_started / job_finished
    #   gateway/* → gateway-specific activity

    # Outputs:
    #   status: "working" | "idle" | "sleeping" | "offline"
    #   detail: str (e.g., "Replying to Discord #general")
    #   since: float (timestamp of last state change)

    # Social affinity:
    #   Query sessions.db for interaction overlap between agents
    #   Maintain affinity_scores: dict[tuple[str, str], float]
    #   Decay factor applied on each recalculation
```

### bot/gateway/pixeltown.py — PixelTown Gateway

```python
class PixelTownGateway:
    """aiohttp server: static files + WebSocket + REST API."""

    # Startup: launched from main.py as async task
    # Static: serves pixeltown/dist/ (Vite build output)
    # WebSocket /ws: bidirectional agent status + user commands
    # REST /api/*: initial data load endpoints

    # WebSocket downstream (server → client):
    #   init, agent_status, social_event, cron_event, message_received

    # WebSocket upstream (client → server):
    #   send_message, trigger_task, toggle_agent, save_layout
```

### Event Hook Integration

Status tracker hooks into existing modules via callback registration. Requires adding callback hook points to `client.py` (processing start/end) and `cron.py` (job start/end) — minimal additions to existing modules:

```python
# In main.py initialization:
status_tracker = AgentStatusTracker(agents)

# Register callbacks:
for agent in agents:
    agent.client.on_processing_start = status_tracker.on_working
    agent.client.on_processing_end = status_tracker.on_idle
    agent.cron_scheduler.on_job_start = status_tracker.on_working
    agent.cron_scheduler.on_job_end = status_tracker.on_idle
```

---

## 10. WebSocket Protocol

### Server → Client

| Type | Fields | Description |
|------|--------|-------------|
| `init` | `agents[]`, `weather`, `season`, `town_layout` | Full state on connect |
| `agent_status` | `agent`, `status`, `detail`, `since` | Agent state change |
| `social_event` | `agents[]`, `action`, `affinity` | Two agents interacting |
| `cron_event` | `agent`, `job`, `action` | Cron job started/finished |
| `message_received` | `agent`, `from`, `preview` | New message notification |

### Client → Server

| Type | Fields | Description |
|------|--------|-------------|
| `send_message` | `agent`, `text`, `channel` | Send message to agent |
| `trigger_task` | `agent`, `job_id` | Trigger a cron job |
| `toggle_agent` | `agent`, `enabled` | Enable/disable agent |
| `save_layout` | `buildings[]` | Persist town layout |

---

## 11. Configuration

New section in `config.yaml`:

```yaml
gateway:
  pixeltown:
    enabled: true
    port: 8765
    host: "127.0.0.1"
    static_dir: "pixeltown/dist"
    weather_mode: "simulated"        # "simulated" | "real"
    weather_api_key: ""              # OpenWeatherMap free tier (optional)
    layout_file: "workspace/town_layout.json"
    idle_behavior:
      wander_interval: [10, 30]      # seconds between idle actions
      social_chance: 0.3             # probability of socializing on encounter
      sleep_after: "23:00"           # time after which agents sleep
```

---

## 12. Asset Strategy

**Source:** Free pixel art packs from itch.io (CC0 or free-for-use license).

| Asset type | Spec | Notes |
|------------|------|-------|
| Characters | 16×16 or 32×32 sprite sheet | 4-direction walk, sit, sleep animations |
| Buildings/map | Stardew-style tileset | Houses, paths, trees, flowers, water |
| Seasonal variants | Same tileset, 4 color palettes | Spring/summer/autumn/winter |
| UI elements | Pixel-style buttons, panels, icons | Dialog frames, status indicators |
| Weather particles | Rain drops, snowflakes, lightning | Small sprite particles |

Agents are differentiated by color tint applied to the same base sprite. V1 uses free assets; custom per-agent sprites can be added later.

---

## 13. Development Workflow

```bash
# Frontend development
cd pixeltown
npm install
npm run dev          # Vite dev server with HMR (proxies WS to MiniClaw)

# Backend
python main.py       # Starts MiniClaw + PixelTown gateway

# Production build
cd pixeltown && npm run build    # Output → pixeltown/dist/
# MiniClaw serves dist/ as static files
```

---

## 14. Scope Summary

Everything included in V1:

- [x] Pixel town with agent cottages, plaza, library, shop
- [x] Agent state machine (idle/working/sleeping/socializing/offline)
- [x] Real-time status from MiniClaw runtime via WebSocket
- [x] Idle behavior simulation (wander, visit, sit)
- [x] Data-driven social system (affinity from session history)
- [x] Day/night cycle (synced to real time)
- [x] Weather system (4 types, simulated or real API)
- [x] Season system (4 seasons, tile set variants)
- [x] Cottage interior view with status details
- [x] Interactive: send messages, trigger tasks, toggle agents
- [x] Sidebar: agent list, activity log, cron tasks, settings
- [x] Customizable town layout (drag-and-drop editor)
- [x] Free pixel art assets from itch.io
