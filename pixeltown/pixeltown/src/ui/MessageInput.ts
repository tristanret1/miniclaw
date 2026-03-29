import type { ClientMessage } from "@/net/Protocol";

type SendFn = (msg: ClientMessage) => void;

/**
 * MessageInput — floating text input for sending messages to agents.
 * Triggered by double-clicking an agent sprite or sidebar entry.
 */
export class MessageInput {
  private el: HTMLElement;
  private inputEl: HTMLInputElement;
  private targetEl: HTMLElement;
  private targetAgent = "";
  private sendFn: SendFn;
  private onSend: ((agentId: string, text: string) => void) | null = null;

  constructor(overlayEl: HTMLElement, sendFn: SendFn) {
    this.sendFn = sendFn;

    this.el = document.createElement("div");
    this.el.id = "message-input-container";
    this.el.style.cssText = `
      display: none;
      position: absolute; bottom: 16px; left: 50%;
      transform: translateX(-50%);
      background: rgba(0,0,0,0.85); border-radius: 8px; padding: 12px;
      color: #fff; font-family: 'Press Start 2P', monospace; font-size: 10px;
      pointer-events: auto; z-index: 20;
    `;
    this.el.innerHTML = `
      <div id="msg-target" style="color: #fbbf24; margin-bottom: 6px;"></div>
      <div style="display: flex; gap: 8px;">
        <input id="msg-input" type="text" placeholder="Type a message..."
          style="
            background: rgba(255,255,255,0.1); border: 1px solid rgba(255,255,255,0.3);
            border-radius: 4px; padding: 6px 8px; color: #fff;
            font-family: 'Press Start 2P', monospace; font-size: 9px;
            width: 280px; outline: none;
          "
        />
        <button id="msg-send" style="
          background: #fbbf24; color: #000; border: none; border-radius: 4px;
          padding: 6px 12px; cursor: pointer;
          font-family: 'Press Start 2P', monospace; font-size: 9px;
        ">Send</button>
        <button id="msg-cancel" style="
          background: rgba(255,255,255,0.2); color: #fff; border: none; border-radius: 4px;
          padding: 6px 8px; cursor: pointer;
          font-family: 'Press Start 2P', monospace; font-size: 9px;
        ">X</button>
      </div>
    `;
    overlayEl.appendChild(this.el);

    this.targetEl = this.el.querySelector("#msg-target")!;
    this.inputEl = this.el.querySelector("#msg-input") as HTMLInputElement;
    const sendBtn = this.el.querySelector("#msg-send")!;
    const cancelBtn = this.el.querySelector("#msg-cancel")!;

    sendBtn.addEventListener("click", () => this.doSend());
    this.inputEl.addEventListener("keydown", (e) => {
      if (e.key === "Enter") this.doSend();
      if (e.key === "Escape") this.close();
    });
    cancelBtn.addEventListener("click", () => this.close());
  }

  /** Open the message input for a specific agent. */
  open(agentId: string, agentName: string): void {
    this.targetAgent = agentId;
    this.targetEl.textContent = `Message ${agentName}:`;
    this.el.style.display = "block";
    this.inputEl.value = "";
    this.inputEl.focus();
  }

  close(): void {
    this.el.style.display = "none";
    this.targetAgent = "";
  }

  setOnSend(cb: (agentId: string, text: string) => void): void {
    this.onSend = cb;
  }

  private doSend(): void {
    const text = this.inputEl.value.trim();
    if (text && this.targetAgent) {
      this.sendFn({
        type: "send_message",
        agent: this.targetAgent,
        text,
        channel: "",
      });
      this.onSend?.(this.targetAgent, text);
      this.inputEl.value = "";
      this.close();
    }
  }
}
