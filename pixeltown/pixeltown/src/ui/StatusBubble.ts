import { STATUS_COLORS } from "@/config";
import type { AgentStatus } from "@/net/Protocol";

/** Color hex string from PixiJS number format. */
function colorHex(c: number): string {
  return "#" + c.toString(16).padStart(6, "0");
}

/**
 * StatusBubble — HTML popup that appears on single-clicking an agent.
 * Shows agent name, current status, detail text, and time since last change.
 * Tracks the agent sprite position on canvas.
 */
export class StatusBubble {
  private el: HTMLElement;
  private visible = false;
  private currentAgentId: string | null = null;

  constructor(overlayEl: HTMLElement) {
    this.el = document.createElement("div");
    this.el.id = "status-bubble";
    this.el.style.cssText = `
      display: none;
      position: absolute;
      background: rgba(0,0,0,0.88);
      border: 2px solid rgba(255,255,255,0.3);
      border-radius: 8px;
      padding: 10px 14px;
      color: #fff;
      font-family: 'Press Start 2P', monospace;
      font-size: 9px;
      pointer-events: auto;
      z-index: 10;
      min-width: 180px;
      transform: translateX(-50%);
    `;
    overlayEl.appendChild(this.el);

    // Click outside to dismiss
    document.addEventListener("pointerdown", (e) => {
      if (this.visible && !this.el.contains(e.target as Node)) {
        this.hide();
      }
    });
  }

  /** Show the bubble for an agent at canvas position (px). */
  show(
    agentId: string,
    name: string,
    status: AgentStatus,
    detail: string,
    since: number,
    canvasX: number,
    canvasY: number,
  ): void {
    this.currentAgentId = agentId;
    const dotColor = colorHex(STATUS_COLORS[status] ?? STATUS_COLORS.offline);
    const elapsed = this.formatElapsed(since);

    this.el.innerHTML = `
      <div style="display:flex;align-items:center;gap:6px;margin-bottom:6px;">
        <span style="width:10px;height:10px;border-radius:50%;background:${dotColor};display:inline-block;"></span>
        <span style="font-size:11px;color:#fbbf24;">${name}</span>
      </div>
      <div style="margin-bottom:4px;">Status: ${status}</div>
      ${detail ? `<div style="color:#aaa;margin-bottom:4px;">${detail}</div>` : ""}
      <div style="color:#666;font-size:8px;">${elapsed}</div>
    `;

    this.el.style.left = `${canvasX}px`;
    this.el.style.top = `${canvasY - 10}px`;
    this.el.style.display = "block";
    this.visible = true;
  }

  hide(): void {
    this.el.style.display = "none";
    this.visible = false;
    this.currentAgentId = null;
  }

  isVisible(): boolean {
    return this.visible;
  }

  getCurrentAgentId(): string | null {
    return this.currentAgentId;
  }

  /** Update position if bubble is tracking an agent. */
  updatePosition(agentId: string, canvasX: number, canvasY: number): void {
    if (this.currentAgentId === agentId && this.visible) {
      this.el.style.left = `${canvasX}px`;
      this.el.style.top = `${canvasY - 10}px`;
    }
  }

  private formatElapsed(since: number): string {
    const ms = Date.now() - since;
    const seconds = Math.floor(ms / 1000);
    if (seconds < 60) return `${seconds}s ago`;
    const minutes = Math.floor(seconds / 60);
    if (minutes < 60) return `${minutes}m ago`;
    const hours = Math.floor(minutes / 60);
    return `${hours}h ago`;
  }
}
