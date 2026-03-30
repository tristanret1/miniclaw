import { Application } from "pixi.js";
import { SCALED_TILE, MAP_COLS, MAP_ROWS } from "@/config";
import { TownScene } from "@/scenes/TownScene";
import { HouseScene } from "@/scenes/HouseScene";
import { WebSocketClient } from "@/net/WebSocketClient";
import { UIOverlay } from "@/ui/UIOverlay";
import { StatusBubble } from "@/ui/StatusBubble";
import { Dashboard } from "@/ui/Dashboard";
import { LayoutEditor } from "@/ui/LayoutEditor";
import type { AgentInfo, ServerMessage } from "@/net/Protocol";
import { loadEditorConfig, getCharacterConfig } from "@/ConfigLoader";
import { applyCharacterConfig } from "@/sprites/SpriteConfig";
import { preloadCoreAssets } from "@/assets/Preloader";

/** Demo agents shown when no backend is connected. */
const DEMO_AGENTS: AgentInfo[] = [
  { id: "agent-1", name: "Claude", status: "idle", detail: "", since: Date.now(), color: 0x4fc3f7 },
  { id: "agent-2", name: "Codex", status: "working", detail: "Processing Discord message", since: Date.now(), color: 0x81c784 },
  { id: "agent-3", name: "Ralph", status: "idle", detail: "", since: Date.now(), color: 0xffb74d },
];

async function init() {
  // Load editor config before initializing scenes (sprite mappings must be set first)
  await loadEditorConfig();
  const charCfg = getCharacterConfig();
  if (charCfg) applyCharacterConfig(charCfg);
  // Preload core assets (spritesheets)
  await preloadCoreAssets();

  const app = new Application();
  await app.init({
    canvas: document.getElementById("game-canvas") as HTMLCanvasElement,
    resizeTo: window,
    backgroundColor: 0x2d5a1b,
    antialias: false,
    resolution: window.devicePixelRatio || 1,
    autoDensity: true,
  });

  const overlayEl = document.getElementById("ui-overlay")!;

  // ── Scenes ──
  const town = new TownScene(app.renderer);
  app.stage.addChild(town.container);
  // Try loading external tilemap first (non-blocking demo fallback if absent)
  await town.loadTilemapIfAvailable();
  town.start();

  // ── Camera: drag to pan + follow agent ──
  const canvas = app.canvas;
  let dragging = false;
  let dragMoved = false;
  let dragStartX = 0;
  let dragStartY = 0;
  let camStartX = 0;
  let camStartY = 0;
  let followAgentId: string | null = null;

  canvas.addEventListener("pointerdown", (e: PointerEvent) => {
    dragging = true;
    dragMoved = false;
    dragStartX = e.clientX;
    dragStartY = e.clientY;
    camStartX = town.container.x;
    camStartY = town.container.y;
  });

  canvas.addEventListener("pointermove", (e: PointerEvent) => {
    if (!dragging) return;
    const dx = e.clientX - dragStartX;
    const dy = e.clientY - dragStartY;
    if (Math.abs(dx) > 3 || Math.abs(dy) > 3) dragMoved = true;
    if (dragMoved) {
      followAgentId = null;
      const mapW = MAP_COLS * SCALED_TILE;
      const mapH = MAP_ROWS * SCALED_TILE;
      town.container.x = Math.min(0, Math.max(canvas.clientWidth - mapW, camStartX + dx));
      town.container.y = Math.min(0, Math.max(canvas.clientHeight - mapH, camStartY + dy));
    }
  });

  canvas.addEventListener("pointerup", () => {
    dragging = false;
    if (dragMoved) {
      town.container.interactiveChildren = false;
      requestAnimationFrame(() => { town.container.interactiveChildren = true; });
    }
  });
  canvas.addEventListener("pointerleave", () => { dragging = false; });

  /** Start following an agent (camera centers on them each frame). */
  function followAgent(agentId: string | null): void {
    followAgentId = agentId;
  }

  /** Smoothly center camera on a world position, clamped to map bounds. */
  function centerCameraOn(worldX: number, worldY: number): void {
    const vw = canvas.clientWidth;
    const vh = canvas.clientHeight;
    const mapW = MAP_COLS * SCALED_TILE;
    const mapH = MAP_ROWS * SCALED_TILE;

    let targetX = vw / 2 - worldX;
    let targetY = vh / 2 - worldY;

    // Clamp so map edges don't go past viewport edges
    targetX = Math.min(0, Math.max(vw - mapW, targetX));
    targetY = Math.min(0, Math.max(vh - mapH, targetY));

    // Smooth lerp
    town.container.x += (targetX - town.container.x) * 0.08;
    town.container.y += (targetY - town.container.y) * 0.08;
  }

  // WebSocket client
  const wsProtocol = location.protocol === "https:" ? "wss:" : "ws:";
  const wsUrl = `${wsProtocol}//${location.host}/ws`;

  const ws = new WebSocketClient(
    wsUrl,
    (msg: ServerMessage) => {
      town.handleMessage(msg);
      ui.handleMessage(msg);

      // Rewire click events after init replaces agents
      if (msg.type === "init") {
        for (const id of town.getAgents().keys()) wireAgentEvents(id);
      }
      // Wire new agents from status updates
      if (msg.type === "agent_status") {
        const a = town.getAgents().get(msg.agent);
        if (a && !(a.container as any).__eventsWired) {
          wireAgentEvents(msg.agent);
        }
      }

      // Update house scene if viewing an agent
      if (msg.type === "agent_status" && house.getCurrentAgentId() === msg.agent) {
        const agent = town.getAgents().get(msg.agent);
        if (agent) {
          house.updateAgent({
            id: agent.id,
            name: agent.name,
            status: agent.status,
            detail: agent.detail,
            since: agent.since,
          });
        }
      }
    },
    (connected: boolean) => {
      ui.setConnected(connected);
      if (!connected && town.getAgents().size === 0) {
        for (const a of DEMO_AGENTS) town.addOrUpdateAgent(a);
        ui.setDemoAgents(DEMO_AGENTS);
      }
    },
  );

  const sendFn = (msg: Parameters<typeof ws.send>[0]) => ws.send(msg);

  // ── UI Components ──
  const ui = new UIOverlay(overlayEl, sendFn);
  const statusBubble = new StatusBubble(overlayEl);
  const dashboard = new Dashboard(overlayEl, sendFn);
  const layoutEditor = new LayoutEditor(overlayEl, sendFn);
  const house = new HouseScene(sendFn);
  house.attachUI(overlayEl);

  // ── Scene Management ──
  let activeScene: "town" | "house" = "town";

  function showTown() {
    activeScene = "town";
    town.container.visible = true;
    house.hide();
  }

  function showHouse(agentId: string) {
    const agent = town.getAgents().get(agentId);
    if (!agent) return;
    activeScene = "house";
    town.container.visible = false;
    statusBubble.hide();
    house.show(
      { id: agent.id, name: agent.name, status: agent.status, detail: agent.detail, since: agent.since },
      town.getCronJobs(),
      agent.indoors,
    );
    app.stage.addChild(house.container);
  }

  house.setOnBack(() => {
    app.stage.removeChild(house.container);
    showTown();
  });

  // ── Wire Cottage Click → Interior View ──
  town.setOnCottageClick((agentId) => {
    if (layoutEditor.isActive()) return;
    showHouse(agentId);
  });

  // ── Wire Subtitle (agent reply displayed at bottom) ──
  let subtitleTimer: ReturnType<typeof setTimeout> | null = null;
  const subtitleEl = document.createElement("div");
  subtitleEl.style.cssText = `
    position: absolute; bottom: 24px; left: 50%; transform: translateX(-50%);
    background: rgba(0,0,0,0.8); color: #f5deb3; padding: 12px 24px;
    border-radius: 8px; border: 2px solid rgba(139,105,20,0.6);
    font-family: 'Press Start 2P', monospace; font-size: 14px;
    max-width: 70%; text-align: center; line-height: 1.8;
    pointer-events: none; display: none; z-index: 100;
    box-shadow: 0 4px 16px rgba(0,0,0,0.5);
  `;
  overlayEl.appendChild(subtitleEl);

  town.setOnSubtitle((agentName, text) => {
    if (subtitleTimer) clearTimeout(subtitleTimer);
    subtitleEl.innerHTML = `<span style="color:#fbbf24;">${agentName}:</span> ${text}`;
    subtitleEl.style.display = "block";
    subtitleTimer = setTimeout(() => {
      subtitleEl.style.display = "none";
    }, Math.min(15000, 3000 + text.length * 80));
  });

  // ── Wire Plaza Click → Dashboard ──
  town.setOnPlazaClick(() => {
    if (layoutEditor.isActive()) return;
    dashboard.setAgents(ui.getAgents());
    dashboard.show();
  });

  // ── Wire Agent Interactions ──
  function wireAgentEvents(agentId: string) {
    const agent = town.getAgents().get(agentId);
    if (!agent) return;
    if ((agent.container as any).__eventsWired) return;
    (agent.container as any).__eventsWired = true;

    let clickCount = 0;
    let clickTimer: ReturnType<typeof setTimeout> | null = null;

    agent.container.on("pointertap", () => {
      clickCount++;
      if (clickCount === 1) {
        clickTimer = setTimeout(() => {
          if (!layoutEditor.isActive()) {
            // Single click → toggle camera follow + show status bubble
            if (followAgentId === agent.id) {
              followAgent(null); // unfollow
            } else {
              followAgent(agent.id); // follow this agent
            }
            statusBubble.show(
              agent.id,
              agent.name,
              agent.status,
              agent.detail,
              agent.since,
              agent.container.x + 24,
              agent.container.y - 20,
            );
          }
          clickCount = 0;
        }, 250);
      } else if (clickCount === 2) {
        // Double click → message input
        if (clickTimer) clearTimeout(clickTimer);
        clickCount = 0;
        statusBubble.hide();
        ui.openMessageInput(agent.id, agent.name);
      }
    });
  }

  // ── Wire Layout Editor ──
  layoutEditor.setBuildings(town.getBuildings());
  ui.setOnEditModeToggle(() => layoutEditor.toggle());

  // ── Wire HouseScene message button ──
  window.addEventListener("pixeltown:open-message", ((e: CustomEvent) => {
    ui.openMessageInput(e.detail.agentId, e.detail.agentName);
  }) as EventListener);

  // ── Load Demo Agents ──
  for (const a of DEMO_AGENTS) town.addOrUpdateAgent(a);
  ui.setDemoAgents(DEMO_AGENTS);
  for (const id of town.getAgents().keys()) wireAgentEvents(id);

  // ── Game Loop ──
  app.ticker.add(() => {
    if (activeScene === "town") {
      town.update();
      // Camera follow
      if (followAgentId && !dragging) {
        const agent = town.getAgents().get(followAgentId);
        if (agent) {
          centerCameraOn(agent.container.x, agent.container.y);
        }
      }
    } else if (activeScene === "house") {
      house.update();
      // Check if agent left the house while we're viewing it
      const viewingId = house.getCurrentAgentId();
      if (viewingId) {
        const townAgent = town.getAgents().get(viewingId);
        if (townAgent && !townAgent.indoors) {
          house.removeIndoorAgent();
        }
      }
    }
  });

  // ── Connect WebSocket ──
  try {
    ws.connect();
  } catch {
    // Demo mode
  }

  console.log("Pixel Town initialized");
}

export default init;
