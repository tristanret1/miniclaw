import { STATUS_COLORS } from "@/config";
import type { AgentInfo, ClientMessage, CronJob } from "@/net/Protocol";

type SendFn = (msg: ClientMessage) => void;

/** Color hex string from PixiJS number format. */
function colorHex(c: number): string {
  return "#" + c.toString(16).padStart(6, "0");
}

/**
 * Dashboard — bulletin board overlay showing global town status.
 * Triggered by clicking the plaza/bulletin board.
 */
export class Dashboard {
  private el: HTMLElement;
  private visible = false;
  private agents = new Map<string, AgentInfo>();
  private cronJobs: CronJob[] = [];
  private sendFn: SendFn;

  constructor(overlayEl: HTMLElement, sendFn: SendFn) {
    this.sendFn = sendFn;

    this.el = document.createElement("div");
    this.el.id = "dashboard-overlay";
    this.el.style.cssText = `
      display: none;
      position: absolute; top: 50%; left: 50%;
      transform: translate(-50%, -50%);
      background: rgba(20,15,10,0.95);
      border: 3px solid #8b6914;
      border-radius: 12px;
      padding: 20px;
      color: #fff;
      font-family: 'Press Start 2P', monospace;
      font-size: 9px;
      pointer-events: auto;
      z-index: 30;
      min-width: 400px;
      max-width: 500px;
      max-height: 80vh;
      overflow-y: auto;
    `;
    overlayEl.appendChild(this.el);
  }

  show(): void {
    this.render();
    this.el.style.display = "block";
    this.visible = true;
  }

  hide(): void {
    this.el.style.display = "none";
    this.visible = false;
  }

  isVisible(): boolean {
    return this.visible;
  }

  setAgents(agents: Map<string, AgentInfo>): void {
    this.agents = agents;
  }

  setCronJobs(jobs: CronJob[]): void {
    this.cronJobs = jobs;
  }

  private render(): void {
    const agentList = Array.from(this.agents.values());
    const active = agentList.filter((a) => a.status !== "offline" && a.status !== "sleeping").length;
    const working = agentList.filter((a) => a.status === "working").length;

    let cronHtml = "";
    if (this.cronJobs.length > 0) {
      cronHtml = `
        <div style="margin-top:14px;border-top:1px solid rgba(255,255,255,0.2);padding-top:10px;">
          <div style="color:#fbbf24;margin-bottom:8px;">Scheduled Tasks</div>
          ${this.cronJobs
            .map(
              (job) => `
            <div style="display:flex;justify-content:space-between;align-items:center;margin:4px 0;">
              <span>${job.name}</span>
              <button class="dash-trigger-btn" data-job="${job.id}" data-agent="${job.agent_id}" style="
                background:#fbbf24;color:#000;border:none;border-radius:3px;
                padding:3px 8px;cursor:pointer;font-family:'Press Start 2P',monospace;font-size:7px;
              ">Run</button>
            </div>
          `,
            )
            .join("")}
        </div>
      `;
    }

    this.el.innerHTML = `
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:14px;">
        <div style="font-size:12px;color:#fbbf24;">Bulletin Board</div>
        <button id="dash-close" style="
          background:none;border:none;color:#fff;cursor:pointer;
          font-family:'Press Start 2P',monospace;font-size:12px;
        ">X</button>
      </div>

      <div style="display:flex;gap:16px;margin-bottom:14px;">
        <div style="text-align:center;">
          <div style="font-size:18px;color:#4ade80;">${active}</div>
          <div style="color:#999;font-size:7px;">Active</div>
        </div>
        <div style="text-align:center;">
          <div style="font-size:18px;color:#fbbf24;">${working}</div>
          <div style="color:#999;font-size:7px;">Working</div>
        </div>
        <div style="text-align:center;">
          <div style="font-size:18px;color:#818cf8;">${agentList.length}</div>
          <div style="color:#999;font-size:7px;">Total</div>
        </div>
      </div>

      <div style="border-top:1px solid rgba(255,255,255,0.2);padding-top:10px;">
        <div style="color:#999;margin-bottom:8px;">Agents</div>
        ${agentList
          .map((a) => {
            const dotColor = colorHex(STATUS_COLORS[a.status] ?? STATUS_COLORS.offline);
            return `
              <div style="display:flex;align-items:center;gap:8px;margin:6px 0;padding:6px;background:rgba(255,255,255,0.05);border-radius:4px;">
                <span style="width:8px;height:8px;border-radius:50%;background:${dotColor};display:inline-block;flex-shrink:0;"></span>
                <div style="flex:1;">
                  <div>${a.name}</div>
                  <div style="color:#999;font-size:7px;">${a.status}${a.detail ? " - " + a.detail : ""}</div>
                </div>
              </div>
            `;
          })
          .join("")}
      </div>

      ${cronHtml}
    `;

    // Wire close button
    this.el.querySelector("#dash-close")!.addEventListener("click", () => this.hide());

    // Wire trigger buttons
    for (const btn of this.el.querySelectorAll(".dash-trigger-btn")) {
      btn.addEventListener("click", () => {
        const jobId = (btn as HTMLElement).dataset.job!;
        const agentId = (btn as HTMLElement).dataset.agent!;
        this.sendFn({ type: "trigger_task", agent: agentId, job_id: jobId });
      });
    }
  }
}
