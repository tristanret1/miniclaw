import { STATUS_COLORS } from "@/config";
import { startMusic, stopMusic } from "@/audio/Music";
import { MessageInput } from "@/ui/MessageInput";
import type {
  AgentInfo,
  ClientMessage,
  CronJob,
  ServerMessage,
  SeasonType,
  WeatherType,
} from "@/net/Protocol";

/** Color hex string from PixiJS number format. */
function colorHex(c: number): string {
  return "#" + c.toString(16).padStart(6, "0");
}

type SendFn = (msg: ClientMessage) => void;

const SEASON_ICONS: Record<string, string> = {
  spring: "\uD83C\uDF38",
  summer: "\u2600\uFE0F",
  autumn: "\uD83C\uDF42",
  winter: "\u2744\uFE0F",
};

/**
 * HTML overlay UI — sidebar with agent list, status, controls,
 * cron tasks, settings, and clock.
 */
export class UIOverlay {
  private root: HTMLElement;
  private agentListEl!: HTMLElement;
  private statusEl!: HTMLElement;
  private clockEl!: HTMLElement;
  private cronListEl!: HTMLElement;
  private agents = new Map<string, AgentInfo>();
  private cronJobs: CronJob[] = [];
  private season: SeasonType = "spring";
  private sendFn: SendFn;
  private messageInput: MessageInput;
  private clockTimer: ReturnType<typeof setInterval> | null = null;

  // Callbacks
  private onEditModeToggle: (() => void) | null = null;

  constructor(overlayEl: HTMLElement, sendFn: SendFn) {
    this.root = overlayEl;
    this.sendFn = sendFn;

    this.buildSidebar();
    this.messageInput = new MessageInput(overlayEl, sendFn);
    this.messageInput.setOnSend((agentId, text) => {
      this.addLogEntry(`Sent message to ${agentId}`);
    });

    // Start clock
    this.updateClock();
    this.clockTimer = setInterval(() => this.updateClock(), 30_000);
  }

  setOnEditModeToggle(cb: () => void): void {
    this.onEditModeToggle = cb;
  }

  private buildSidebar(): void {
    this.root.innerHTML = `
      <div id="sidebar" style="
        position: absolute; top: 10px; left: 10px;
        background: linear-gradient(180deg, #5c3a1e 0%, #4a2e16 100%);
        border: 3px solid #8b6914;
        border-radius: 4px;
        padding: 0;
        color: #f5deb3; font-size: 10px; min-width: 200px;
        font-family: 'Press Start 2P', monospace;
        max-height: calc(100vh - 20px); overflow-y: auto;
        pointer-events: auto;
        box-shadow: inset 0 0 0 2px #3e2510, 0 4px 12px rgba(0,0,0,0.5);
        image-rendering: pixelated;
      ">
        <!-- Title bar -->
        <div id="sidebar-title" style="
          background: linear-gradient(90deg, #8b6914, #daa520, #8b6914);
          padding: 6px 10px; text-align: center;
          border-bottom: 2px solid #654321;
          font-size: 11px; color: #3e2510;
          text-shadow: 1px 1px 0 #ffd700;
          cursor: pointer; user-select: none;
          display: flex; justify-content: space-between; align-items: center;
        "><span style="flex:1;text-align:center;">Pixel Town</span><span id="sidebar-toggle" style="font-size:8px;">&#x25B2;</span></div>

        <div id="sidebar-body" style="padding: 8px 10px;">
          <!-- Clock -->
          <div id="clock" style="color:#daa520;margin-bottom:6px;font-size:8px;text-align:center;"></div>

          <!-- Connection status -->
          <div id="ws-status" style="color: #cd853f; margin-bottom: 8px; font-size: 8px; text-align: center;">Offline (demo)</div>

          <!-- Agents section -->
          <div style="
            background: rgba(0,0,0,0.25); border-radius: 3px;
            border: 1px solid #654321; padding: 6px; margin-bottom: 6px;
          ">
            <div style="color: #daa520; margin-bottom: 4px; font-size: 8px;">Agents</div>
            <div id="agent-list"></div>
          </div>

          <!-- Cron Tasks section -->
          <div style="
            background: rgba(0,0,0,0.25); border-radius: 3px;
            border: 1px solid #654321; padding: 6px; margin-bottom: 6px;
          ">
            <div style="color: #daa520; margin-bottom: 4px; font-size: 8px;">Tasks</div>
            <div id="cron-list" style="font-size:8px;color:#cd853f;">No scheduled tasks</div>
          </div>

          <!-- Activity Log -->
          <div id="activity-log" style="
            background: rgba(0,0,0,0.25); border-radius: 3px;
            border: 1px solid #654321; padding: 6px; margin-bottom: 6px;
          ">
            <div style="color: #daa520; margin-bottom: 4px; font-size: 8px;">Activity</div>
            <div id="log-entries"></div>
          </div>

          <!-- Settings -->
          <div style="
            background: rgba(0,0,0,0.25); border-radius: 3px;
            border: 1px solid #654321; padding: 6px;
          ">
            <div style="color: #daa520; margin-bottom: 4px; font-size: 8px;">Settings</div>
            <div style="display:flex;flex-direction:column;gap:4px;">
              <label style="display:flex;align-items:center;gap:6px;cursor:pointer;font-size:7px;color:#cd853f;">
                <input type="checkbox" id="setting-sound" style="accent-color:#daa520;" />
                Sound
              </label>
            </div>
          </div>
        </div>
      </div>
    `;

    this.agentListEl = this.root.querySelector("#agent-list")!;
    this.statusEl = this.root.querySelector("#ws-status")!;
    this.clockEl = this.root.querySelector("#clock")!;
    this.cronListEl = this.root.querySelector("#cron-list")!;

    // Wire sidebar collapse
    const titleBar = this.root.querySelector("#sidebar-title")!;
    const sidebarBody = this.root.querySelector("#sidebar-body") as HTMLElement;
    const toggleIcon = this.root.querySelector("#sidebar-toggle")!;
    titleBar.addEventListener("click", () => {
      const collapsed = sidebarBody.style.display === "none";
      sidebarBody.style.display = collapsed ? "" : "none";
      toggleIcon.textContent = collapsed ? "\u25B2" : "\u25BC";
    });

    // Wire sound toggle
    const soundCheckbox = this.root.querySelector("#setting-sound") as HTMLInputElement;
    soundCheckbox.addEventListener("change", () => {
      if (soundCheckbox.checked) {
        startMusic();
      } else {
        stopMusic();
      }
    });

  }

  /** Open the message input for a specific agent. */
  openMessageInput(agentId: string, agentName: string): void {
    this.messageInput.open(agentId, agentName);
  }

  /** Set WebSocket connection status. */
  setConnected(connected: boolean): void {
    this.statusEl.textContent = connected ? "Connected" : "Offline (demo mode)";
    this.statusEl.style.color = connected ? "#4ade80" : "#fbbf24";
  }

  /** Handle all server messages. */
  handleMessage(msg: ServerMessage): void {
    switch (msg.type) {
      case "init":
        this.agents.clear();
        for (const a of msg.agents) {
          this.agents.set(a.id, a);
        }
        this.season = msg.season;
        this.renderAgentList();
        this.updateClock();
        this.addLogEntry("Connected to server");
        break;

      case "agent_status": {
        const existing = this.agents.get(msg.agent);
        if (existing) {
          existing.status = msg.status;
          existing.detail = msg.detail;
          existing.since = msg.since;
        } else {
          this.agents.set(msg.agent, {
            id: msg.agent,
            name: msg.agent,
            status: msg.status,
            detail: msg.detail,
            since: msg.since,
          });
        }
        this.renderAgentList();
        this.addLogEntry(`${msg.agent}: ${msg.status}${msg.detail ? " — " + msg.detail : ""}`);
        break;
      }

      case "social_event":
        this.addLogEntry(`${msg.agents[0]} & ${msg.agents[1]}: ${msg.action}`);
        break;

      case "cron_event":
        this.addLogEntry(`${msg.agent}: cron ${msg.job} ${msg.action}`);
        break;

      case "message_received":
        this.addLogEntry(`${msg.agent} got msg from ${msg.from}`);
        break;
    }
  }

  /** Set demo agents (when no WS connection). */
  setDemoAgents(agents: AgentInfo[]): void {
    this.agents.clear();
    for (const a of agents) {
      this.agents.set(a.id, a);
    }
    this.renderAgentList();
  }

  /** Update cron jobs list. */
  setCronJobs(jobs: CronJob[]): void {
    this.cronJobs = jobs;
    this.renderCronList();
  }

  setSeason(season: SeasonType): void {
    this.season = season;
    this.updateClock();
  }

  getAgents(): Map<string, AgentInfo> {
    return this.agents;
  }

  private renderAgentList(): void {
    this.agentListEl.innerHTML = "";
    for (const agent of this.agents.values()) {
      const dotColor = colorHex(STATUS_COLORS[agent.status] ?? STATUS_COLORS.offline);
      const row = document.createElement("div");
      row.style.cssText = `
        display:flex;align-items:center;gap:6px;margin:3px 0;cursor:pointer;
        padding:3px 4px;border-radius:2px;font-size:8px;color:#f5deb3;
        transition:background 0.1s;
      `;
      row.innerHTML = `
        <span style="width:8px;height:8px;border-radius:50%;background:${dotColor};display:inline-block;flex-shrink:0;box-shadow:0 0 4px ${dotColor};"></span>
        <span>${agent.name}</span>
        <span style="color:#cd853f;font-size:7px;margin-left:auto;">${agent.status}</span>
      `;
      row.title = agent.detail || agent.status;
      row.addEventListener("mouseenter", () => { row.style.background = "rgba(218,165,32,0.15)"; });
      row.addEventListener("mouseleave", () => { row.style.background = ""; });
      row.addEventListener("dblclick", () => {
        this.openMessageInput(agent.id, agent.name);
      });
      this.agentListEl.appendChild(row);
    }
  }

  private renderCronList(): void {
    if (this.cronJobs.length === 0) {
      this.cronListEl.innerHTML = '<span style="color:#666;">No scheduled tasks</span>';
      return;
    }
    this.cronListEl.innerHTML = "";
    for (const job of this.cronJobs) {
      const row = document.createElement("div");
      row.style.cssText = "display:flex;justify-content:space-between;align-items:center;margin:3px 0;";
      row.innerHTML = `
        <span>${job.name}</span>
        <button class="cron-trigger-btn" data-job="${job.id}" data-agent="${job.agent_id}" style="
          background:#fbbf24;color:#000;border:none;border-radius:3px;
          padding:2px 6px;cursor:pointer;font-family:'Press Start 2P',monospace;font-size:7px;
        ">Run</button>
      `;
      this.cronListEl.appendChild(row);
    }
    for (const btn of this.cronListEl.querySelectorAll(".cron-trigger-btn")) {
      btn.addEventListener("click", () => {
        const el = btn as HTMLElement;
        this.sendFn({
          type: "trigger_task",
          agent: el.dataset.agent!,
          job_id: el.dataset.job!,
        });
        this.addLogEntry(`Triggered task ${el.dataset.job}`);
      });
    }
  }

  private updateClock(): void {
    const now = new Date();
    const time = now.toLocaleTimeString("en-US", {
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    });
    const icon = SEASON_ICONS[this.season] ?? "";
    this.clockEl.textContent = `${time} ${icon} ${this.season}`;
  }

  addLogEntry(text: string): void {
    const logEntries = this.root.querySelector("#log-entries");
    if (!logEntries) return;

    const entry = document.createElement("div");
    const time = new Date().toLocaleTimeString("en-US", {
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    });
    entry.textContent = `[${time}] ${text}`;
    entry.style.cssText = "margin: 2px 0; color: #cd853f; font-size: 7px;";
    logEntries.prepend(entry);

    while (logEntries.children.length > 20) {
      logEntries.removeChild(logEntries.lastChild!);
    }
  }
}
