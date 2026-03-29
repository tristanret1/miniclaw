import { WS_RECONNECT_DELAY, WS_MAX_RECONNECT_DELAY } from "@/config";
import type { ServerMessage, ClientMessage } from "./Protocol";

type MessageHandler = (msg: ServerMessage) => void;
type StatusHandler = (connected: boolean) => void;

/**
 * WebSocket client with automatic reconnection.
 * Connects to the PixelTown gateway and dispatches typed messages.
 */
export class WebSocketClient {
  private ws: WebSocket | null = null;
  private url: string;
  private reconnectDelay = WS_RECONNECT_DELAY;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private intentionallyClosed = false;

  private onMessage: MessageHandler;
  private onStatus: StatusHandler;

  constructor(url: string, onMessage: MessageHandler, onStatus: StatusHandler) {
    this.url = url;
    this.onMessage = onMessage;
    this.onStatus = onStatus;
  }

  connect(): void {
    this.intentionallyClosed = false;
    this.createConnection();
  }

  disconnect(): void {
    this.intentionallyClosed = true;
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
  }

  send(msg: ClientMessage): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(msg));
    }
  }

  private createConnection(): void {
    try {
      this.ws = new WebSocket(this.url);
    } catch {
      this.scheduleReconnect();
      return;
    }

    this.ws.onopen = () => {
      this.reconnectDelay = WS_RECONNECT_DELAY;
      this.onStatus(true);
    };

    this.ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data as string) as ServerMessage;
        this.onMessage(msg);
      } catch {
        console.warn("[WS] Failed to parse message:", event.data);
      }
    };

    this.ws.onclose = () => {
      this.onStatus(false);
      if (!this.intentionallyClosed) {
        this.scheduleReconnect();
      }
    };

    this.ws.onerror = () => {
      // onclose will fire after this
    };
  }

  private scheduleReconnect(): void {
    if (this.reconnectTimer) return;
    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null;
      this.reconnectDelay = Math.min(this.reconnectDelay * 2, WS_MAX_RECONNECT_DELAY);
      this.createConnection();
    }, this.reconnectDelay);
  }
}
