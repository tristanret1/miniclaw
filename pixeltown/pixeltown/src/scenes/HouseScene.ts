import { Container, Graphics, Text } from "pixi.js";
import { SCALED_TILE, STATUS_COLORS } from "@/config";
import type { AgentInfo, AgentStatus, ClientMessage, CronJob } from "@/net/Protocol";
import { Agent } from "@/entities/Agent";

type SendFn = (msg: ClientMessage) => void;

/** Color hex string from PixiJS number format. */
function colorHex(c: number): string {
  return "#" + c.toString(16).padStart(6, "0");
}

/**
 * HouseScene — cottage interior view for a single agent.
 * Shows pixel furniture, status panel, and action buttons.
 */
export class HouseScene {
  readonly container: Container;
  private uiEl: HTMLElement;
  private agent: AgentInfo | null = null;
  private cronJobs: CronJob[] = [];
  private sendFn: SendFn;
  private onBack: (() => void) | null = null;

  // Indoor agent sprite
  private indoorAgent: Agent | null = null;
  private indoorWanderTimer: ReturnType<typeof setInterval> | null = null;
  private roomBounds = { x: 0, y: 0, w: 0, h: 0 };

  constructor(sendFn: SendFn) {
    this.container = new Container();
    this.sendFn = sendFn;

    // Create UI element (will be attached to overlay when shown)
    this.uiEl = document.createElement("div");
    this.uiEl.id = "house-scene-ui";
    this.uiEl.style.cssText = `
      display: none;
      position: absolute; bottom: 0; left: 0; right: 0;
      pointer-events: auto;
      font-family: 'Press Start 2P', monospace;
      font-size: 9px;
    `;

  }

  attachUI(overlayEl: HTMLElement): void {
    overlayEl.appendChild(this.uiEl);
  }

  setOnBack(cb: () => void): void {
    this.onBack = cb;
  }

  show(agent: AgentInfo, cronJobs: CronJob[] = [], isIndoors = false): void {
    this.agent = agent;
    this.cronJobs = cronJobs;
    // Redraw room with agent-specific theme
    this.container.removeChildren();
    this.drawRoom(agent.id);
    // Only show agent sprite if they're actually inside
    if (isIndoors) {
      this.spawnIndoorAgent(agent);
    }
    this.container.visible = true;
    this.uiEl.style.display = "block";
    this.renderUI();
  }

  hide(): void {
    this.container.visible = false;
    this.uiEl.style.display = "none";
    this.clearIndoorAgent();
  }

  /** Called every frame from the game loop when house scene is active. */
  update(): void {
    if (this.indoorAgent) {
      this.indoorAgent.update();
    }
  }

  private spawnIndoorAgent(info: AgentInfo): void {
    this.clearIndoorAgent();
    const T = SCALED_TILE;
    // Place agent in the middle of the room
    const startTileX = Math.floor((this.roomBounds.x + this.roomBounds.w / 2) / T);
    const startTileY = Math.floor((this.roomBounds.y + this.roomBounds.h * 0.6) / T);
    this.indoorAgent = new Agent(info.id, info.name, startTileX, startTileY, info.color);
    this.indoorAgent.setStatus(info.status, info.detail, info.since);
    this.container.addChild(this.indoorAgent.container);

    // Wander around the room every few seconds
    this.startIndoorWander();
  }

  private clearIndoorAgent(): void {
    if (this.indoorWanderTimer) {
      clearInterval(this.indoorWanderTimer);
      this.indoorWanderTimer = null;
    }
    if (this.indoorAgent) {
      this.container.removeChild(this.indoorAgent.container);
      this.indoorAgent = null;
    }
  }

  private startIndoorWander(): void {
    const T = SCALED_TILE;
    const wander = () => {
      if (!this.indoorAgent) return;
      // Pick a random walkable point within room bounds
      const minTX = Math.floor(this.roomBounds.x / T) + 1;
      const maxTX = Math.floor((this.roomBounds.x + this.roomBounds.w) / T) - 1;
      const minTY = Math.floor((this.roomBounds.y + this.roomBounds.h * 0.35) / T);
      const maxTY = Math.floor((this.roomBounds.y + this.roomBounds.h) / T) - 1;

      if (maxTX <= minTX || maxTY <= minTY) return;

      const targetX = minTX + Math.floor(Math.random() * (maxTX - minTX));
      const targetY = minTY + Math.floor(Math.random() * (maxTY - minTY));

      // Simple straight-line path (no obstacles in room)
      const path: { x: number; y: number }[] = [];
      const curX = this.indoorAgent.tileX;
      const curY = this.indoorAgent.tileY;
      path.push({ x: curX, y: curY });

      // Walk horizontally first, then vertically
      const dx = targetX > curX ? 1 : -1;
      let x = curX;
      while (x !== targetX) {
        x += dx;
        path.push({ x, y: curY });
      }
      const dy = targetY > curY ? 1 : -1;
      let y = curY;
      while (y !== targetY) {
        y += dy;
        path.push({ x: targetX, y });
      }

      if (path.length > 1) {
        this.indoorAgent.setPath(path);
      }
    };

    // First wander after a short delay, then every 3-6 seconds
    setTimeout(wander, 1000);
    this.indoorWanderTimer = setInterval(wander, 3000 + Math.random() * 3000);
  }

  updateAgent(agent: AgentInfo): void {
    if (this.agent && this.agent.id === agent.id) {
      this.agent = agent;
      this.renderUI();
    }
  }

  getCurrentAgentId(): string | null {
    return this.agent?.id ?? null;
  }

  /** Room theme palette — varies per agent. */
  private getTheme(agentId: string) {
    const themes = [
      { // warm / classic
        wall: 0xd4c5a9, wainscot: 0xc4b599, floorA: 0x9b7b55, floorB: 0x8b6b45,
        rug: 0x8b2252, rugAccent: 0xdaa520, blanket: 0x4169e1, blanketDark: 0x2c4ba0,
        sofa: 0xc0392b, sofaFrame: 0x6b3a2a, pillow: 0xe8c840,
        painting: 0x87ceeb, paintingMtn: 0x4a7a4a, bedroomRug: 0x9370db,
      },
      { // cozy / forest
        wall: 0xc8d5c0, wainscot: 0xb0c4a8, floorA: 0x8a7a5a, floorB: 0x7a6a4a,
        rug: 0x2e5e4e, rugAccent: 0x8fbc8f, blanket: 0xd2691e, blanketDark: 0xa0522d,
        sofa: 0x5f9ea0, sofaFrame: 0x3a6a6e, pillow: 0xfaf0e6,
        painting: 0xffd700, paintingMtn: 0x8b4513, bedroomRug: 0x8fbc8f,
      },
      { // elegant / lavender
        wall: 0xd8cce8, wainscot: 0xc8b8d8, floorA: 0x9a8a7a, floorB: 0x8a7a6a,
        rug: 0x6a3d7a, rugAccent: 0xdda0dd, blanket: 0x9370db, blanketDark: 0x7b60bb,
        sofa: 0xda70d6, sofaFrame: 0x8b4585, pillow: 0xfffaf0,
        painting: 0xffb6c1, paintingMtn: 0x9370db, bedroomRug: 0xdda0dd,
      },
    ];
    // Hash agent ID to pick a theme
    let hash = 0;
    for (let i = 0; i < agentId.length; i++) hash = (hash * 31 + agentId.charCodeAt(i)) | 0;
    return themes[Math.abs(hash) % themes.length];
  }

  private drawRoom(agentId = ""): void {
    const theme = this.getTheme(agentId);
    const viewW = window.innerWidth;
    const viewH = window.innerHeight;
    const margin = SCALED_TILE;
    const roomW = Math.min(viewW - margin * 2, 22 * SCALED_TILE);
    const roomH = Math.min(viewH - margin * 4, 14 * SCALED_TILE);
    const ox = Math.floor((viewW - roomW) / 2 / SCALED_TILE) * SCALED_TILE;
    const oy = margin;
    const T = SCALED_TILE;
    const PX = T / 16;
    const wallH = T * 2.5;
    const dividerX = ox + roomW * 0.55;

    // Store room bounds for indoor agent wandering
    this.roomBounds = { x: ox, y: oy, w: roomW, h: roomH };

    const g = new Graphics();

    // ── Floor ──
    g.rect(ox, oy + wallH, dividerX - ox, roomH - wallH);
    g.fill(theme.floorA);
    g.rect(dividerX, oy + wallH, ox + roomW - dividerX, roomH - wallH);
    g.fill(theme.floorB);

    // Floor board lines
    for (let r = 0; r < Math.ceil(roomH / T); r++) {
      const y = oy + wallH + r * T;
      if (y > oy + roomH) break;
      g.moveTo(ox, y);
      g.lineTo(ox + roomW, y);
      g.stroke({ width: 1, color: 0x7a6040, alpha: 0.35 });
    }

    // ── Rug in living room ──
    const rugX = ox + T * 2;
    const rugY = oy + wallH + T * 2.5;
    const rugW = (dividerX - ox) - T * 4;
    const rugRH = T * 3;
    g.roundRect(rugX, rugY, rugW, rugRH, PX * 4);
    g.fill(theme.rug);
    g.roundRect(rugX + PX * 4, rugY + PX * 4, rugW - PX * 8, rugRH - PX * 8, PX * 2);
    g.stroke({ width: 2, color: theme.rugAccent, alpha: 0.6 });
    // Rug pattern
    g.roundRect(rugX + PX * 8, rugY + PX * 8, rugW - PX * 16, rugRH - PX * 16, PX * 2);
    g.stroke({ width: 1, color: 0xcd853f, alpha: 0.4 });

    // ── Back wall ──
    g.rect(ox, oy, roomW, wallH);
    g.fill(theme.wall);
    // Wainscoting
    g.rect(ox, oy + wallH - PX * 6, roomW, PX * 6);
    g.fill(theme.wainscot);
    g.moveTo(ox, oy + wallH - PX * 6);
    g.lineTo(ox + roomW, oy + wallH - PX * 6);
    g.stroke({ width: 2, color: 0x8b7355 });
    // Wall outline
    g.rect(ox, oy, roomW, wallH);
    g.stroke({ width: 3, color: 0x5c3a1e });

    // ── Room divider wall ──
    g.rect(dividerX - PX * 2, oy, PX * 4, roomH);
    g.fill(theme.wainscot);
    g.stroke({ width: 2, color: 0x5c3a1e });
    // Doorway in divider
    const innerDoorY = oy + wallH + T;
    const innerDoorH = T * 2.5;
    g.rect(dividerX - PX * 2, innerDoorY, PX * 4, innerDoorH);
    g.fill(theme.floorA);

    // ── Outer walls ──
    g.rect(ox, oy, roomW, roomH);
    g.stroke({ width: 3, color: 0x5c3a1e });

    // ── Windows on back wall ──
    const drawWin = (wx: number, wy: number, ww: number, wh: number) => {
      // Frame
      g.rect(wx - PX * 2, wy - PX * 2, ww + PX * 4, wh + PX * 4);
      g.fill(0x8b6914);
      // Glass
      g.rect(wx, wy, ww, wh);
      g.fill(0x87ceeb);
      // Cross
      g.moveTo(wx + ww / 2, wy);
      g.lineTo(wx + ww / 2, wy + wh);
      g.moveTo(wx, wy + wh / 2);
      g.lineTo(wx + ww, wy + wh / 2);
      g.stroke({ width: 2, color: 0x5c3a1e });
      // Curtains
      g.rect(wx, wy, PX * 6, wh);
      g.fill({ color: 0xfaf0e6, alpha: 0.5 });
      g.rect(wx + ww - PX * 6, wy, PX * 6, wh);
      g.fill({ color: 0xfaf0e6, alpha: 0.5 });
      // Curtain rod
      g.rect(wx - PX * 4, wy - PX * 4, ww + PX * 8, PX * 2);
      g.fill(0x8b6914);
    };
    // Living room window
    drawWin(ox + T * 2, oy + PX * 8, T * 2, T * 1.5);
    // Bedroom window
    drawWin(dividerX + T * 2, oy + PX * 8, T * 2, T * 1.5);

    // ── Front entrance (opening in bottom wall) ──
    const doorW = T * 1.5;
    const doorX = ox + (dividerX - ox) / 2 - doorW / 2;
    const doorY = oy + roomH;
    // Cut the opening — draw floor extending outward to porch
    g.rect(doorX, doorY - PX * 4, doorW, PX * 8);
    g.fill(theme.floorA);
    // Door frame on both sides of opening
    g.rect(doorX - PX * 4, doorY - PX * 6, PX * 4, PX * 10);
    g.fill(0x8b6914);
    g.rect(doorX + doorW, doorY - PX * 6, PX * 4, PX * 10);
    g.fill(0x8b6914);
    // Threshold strip
    g.rect(doorX, doorY - PX * 2, doorW, PX * 2);
    g.fill(0x654321);
    // Welcome mat inside
    g.roundRect(doorX + PX * 2, doorY - T * 0.8, doorW - PX * 4, T * 0.6, PX * 2);
    g.fill(0x8b4513);
    g.stroke({ width: 1, color: 0x654321 });

    this.container.addChild(g);

    // ── Furniture ──
    this.drawLivingRoom(g, ox, oy, dividerX - ox, roomH, wallH, theme);
    this.drawBedroom(g, dividerX, oy, ox + roomW - dividerX, roomH, wallH, theme);

    // Room label
    const label = new Text({
      text: "Cottage Interior",
      style: { fontFamily: '"Press Start 2P", monospace', fontSize: 10, fill: 0xffffff },
    });
    label.x = ox;
    label.y = oy - T * 0.8;
    this.container.addChild(label);
  }

  private drawLivingRoom(g: Graphics, ox: number, oy: number, rw: number, rh: number, wallH: number, theme: ReturnType<HouseScene["getTheme"]>): void {
    const T = SCALED_TILE;
    const PX = T / 16;

    // ── Sofa (against left wall) ──
    const sofaX = ox + PX * 6;
    const sofaY = oy + wallH + T * 1;
    const sofaW = T * 1.2;
    const sofaH = T * 3;
    // Back
    g.rect(sofaX, sofaY, PX * 8, sofaH);
    g.fill(theme.sofaFrame);
    // Cushions
    g.roundRect(sofaX + PX * 8, sofaY + PX * 2, sofaW - PX * 8, sofaH / 2 - PX * 2, PX * 3);
    g.fill(theme.sofa);
    g.roundRect(sofaX + PX * 8, sofaY + sofaH / 2 + PX, sofaW - PX * 8, sofaH / 2 - PX * 3, PX * 3);
    g.fill(theme.sofa);
    // Arm rests
    g.roundRect(sofaX, sofaY - PX * 3, sofaW, PX * 5, PX * 2);
    g.fill(theme.sofaFrame);
    g.roundRect(sofaX, sofaY + sofaH - PX * 2, sofaW, PX * 5, PX * 2);
    g.fill(theme.sofaFrame);
    // Throw pillow
    g.roundRect(sofaX + PX * 10, sofaY + PX * 6, PX * 10, PX * 10, PX * 3);
    g.fill(theme.pillow);

    // ── Coffee table (center) ──
    const ctX = ox + rw / 2 - T * 1;
    const ctY = oy + wallH + T * 2;
    g.roundRect(ctX, ctY, T * 2, T * 1.2, PX * 2);
    g.fill(0xa0522d);
    g.stroke({ width: 2, color: 0x5c3a1e });
    // Cup on table
    g.rect(ctX + PX * 6, ctY + PX * 4, PX * 6, PX * 8);
    g.fill(0xffffff);
    g.stroke({ width: 1, color: 0xcccccc });
    // Saucer
    g.ellipse(ctX + PX * 9, ctY + PX * 13, PX * 5, PX * 2);
    g.fill(0xffffff);
    // Book on table
    g.rect(ctX + T + PX * 4, ctY + PX * 3, PX * 14, PX * 10);
    g.fill(0x2e4057);
    g.stroke({ width: 1, color: 0x1a2a3a });

    // ── Bookshelf on back wall ──
    const bsX = ox + rw - T * 2.5;
    const bsY = oy + PX * 6;
    const bsW = T * 2;
    const bsH = wallH - PX * 12;
    g.rect(bsX, bsY, bsW, bsH);
    g.fill(0x654321);
    g.stroke({ width: 2, color: 0x4a3018 });
    // Shelves
    for (let s = 0; s < 3; s++) {
      const sy = bsY + (s + 1) * (bsH / 3);
      g.rect(bsX, sy - PX * 2, bsW, PX * 2);
      g.fill(0x7a5a38);
    }
    // Books
    const bookColors = [0xcc3333, 0x3366cc, 0x339933, 0xcc9933, 0x9933cc, 0xcc6633, 0x3399cc, 0xcc3366];
    for (let s = 0; s < 3; s++) {
      const sy = bsY + s * (bsH / 3) + PX * 2;
      for (let b = 0; b < 5; b++) {
        const bx = bsX + PX * 3 + b * PX * 6;
        const bh = PX * 8 + (b % 3) * PX;
        g.rect(bx, sy + (bsH / 3 - PX * 4 - bh), PX * 4, bh);
        g.fill(bookColors[(s * 5 + b) % bookColors.length]);
      }
    }

    // ── Wall clock ──
    const clockX = ox + rw / 2;
    const clockY = oy + PX * 14;
    g.circle(clockX, clockY, PX * 8);
    g.fill(0xfaf0e6);
    g.circle(clockX, clockY, PX * 8);
    g.stroke({ width: 2, color: 0x8b6914 });
    // Clock hands
    g.moveTo(clockX, clockY);
    g.lineTo(clockX, clockY - PX * 5);
    g.stroke({ width: 2, color: 0x333333 });
    g.moveTo(clockX, clockY);
    g.lineTo(clockX + PX * 3, clockY + PX * 2);
    g.stroke({ width: 1.5, color: 0x333333 });
    g.circle(clockX, clockY, PX * 1);
    g.fill(0x333333);

    // ── Fireplace (right side of living room) ──
    const fpX = ox + rw - T * 0.5 - PX * 4;
    const fpY = oy + wallH + T * 1;
    // Mantel
    g.rect(fpX - T, fpY - PX * 4, T * 1.5, PX * 4);
    g.fill(0x808080);
    // Firebox
    g.rect(fpX - T + PX * 4, fpY, T * 1.5 - PX * 8, T * 1.8);
    g.fill(0x333333);
    // Bricks
    g.rect(fpX - T, fpY, T * 1.5, T * 2);
    g.stroke({ width: 2, color: 0x808080 });
    // Fire glow
    g.circle(fpX - T / 2 + PX * 4, fpY + T * 1.2, PX * 6);
    g.fill({ color: 0xff6600, alpha: 0.6 });
    g.circle(fpX - T / 2 + PX * 2, fpY + T, PX * 4);
    g.fill({ color: 0xffcc00, alpha: 0.5 });
    // Logs
    g.roundRect(fpX - T + PX * 8, fpY + T * 1.4, T - PX * 8, PX * 4, PX);
    g.fill(0x5c3a1e);
    g.roundRect(fpX - T + PX * 6, fpY + T * 1.2, T - PX * 4, PX * 3, PX);
    g.fill(0x6b4226);


    // ── Picture frame on back wall ──
    const pfX = ox + PX * 12;
    const pfY = oy + PX * 8;
    g.rect(pfX, pfY, T * 1.2, T * 0.9);
    g.fill(0x8b6914);
    g.rect(pfX + PX * 3, pfY + PX * 3, T * 1.2 - PX * 6, T * 0.9 - PX * 6);
    g.fill(theme.painting);
    // Simple mountain in painting
    g.moveTo(pfX + PX * 5, pfY + T * 0.6);
    g.lineTo(pfX + PX * 12, pfY + PX * 6);
    g.lineTo(pfX + PX * 19, pfY + T * 0.6);
    g.closePath();
    g.fill(theme.paintingMtn);
  }

  private drawBedroom(g: Graphics, ox: number, oy: number, rw: number, rh: number, wallH: number, theme: ReturnType<HouseScene["getTheme"]>): void {
    const T = SCALED_TILE;
    const PX = T / 16;

    // ── Bed (against right wall) ──
    const bedX = ox + rw - T * 2.5;
    const bedY = oy + wallH + T * 0.8;
    const bedW = T * 2;
    const bedH = T * 3.5;
    // Frame
    g.roundRect(bedX, bedY, bedW, bedH, PX * 2);
    g.fill(0x8b6914);
    g.stroke({ width: 2, color: 0x654321 });
    // Headboard
    g.roundRect(bedX, bedY, bedW, PX * 8, PX * 3);
    g.fill(0x654321);
    // Mattress
    g.rect(bedX + PX * 3, bedY + PX * 10, bedW - PX * 6, bedH - PX * 14);
    g.fill(0xfaf0e6);
    // Blanket
    g.rect(bedX + PX * 3, bedY + PX * 10 + (bedH - PX * 14) * 0.4, bedW - PX * 6, (bedH - PX * 14) * 0.6);
    g.fill(theme.blanket);
    g.stroke({ width: 1, color: theme.blanketDark });
    // Blanket fold
    g.moveTo(bedX + PX * 3, bedY + PX * 10 + (bedH - PX * 14) * 0.4 + PX * 2);
    g.lineTo(bedX + bedW - PX * 3, bedY + PX * 10 + (bedH - PX * 14) * 0.4 + PX * 2);
    g.stroke({ width: 1, color: 0xffffff, alpha: 0.3 });
    // Pillows
    g.roundRect(bedX + PX * 5, bedY + PX * 12, PX * 12, PX * 8, PX * 3);
    g.fill(0xffffff);
    g.stroke({ width: 1, color: 0xe0e0e0 });
    g.roundRect(bedX + PX * 20, bedY + PX * 12, PX * 12, PX * 8, PX * 3);
    g.fill(0xffffff);
    g.stroke({ width: 1, color: 0xe0e0e0 });

    // ── Nightstand ──
    const nsX = bedX - T * 0.8;
    const nsY = bedY;
    g.rect(nsX, nsY, T * 0.7, T * 1);
    g.fill(0x8b6914);
    g.stroke({ width: 1, color: 0x654321 });
    // Drawer
    g.rect(nsX + PX * 2, nsY + T * 0.5, T * 0.7 - PX * 4, PX * 6);
    g.stroke({ width: 1, color: 0x654321 });
    g.circle(nsX + T * 0.35, nsY + T * 0.5 + PX * 3, PX);
    g.fill(0xdaa520);
    // Lamp on nightstand
    g.rect(nsX + PX * 6, nsY - PX * 10, PX * 3, PX * 10);
    g.fill(0x808080);
    // Lampshade
    g.moveTo(nsX + PX * 2, nsY - PX * 10);
    g.lineTo(nsX + PX * 7, nsY - PX * 18);
    g.lineTo(nsX + PX * 12, nsY - PX * 10);
    g.closePath();
    g.fill(0xfff8dc);
    g.stroke({ width: 1, color: 0xdaa520 });

    // ── Wardrobe (against back wall) ──
    const wdX = ox + PX * 8;
    const wdY = oy + PX * 4;
    const wdW = T * 1.8;
    const wdH = wallH - PX * 8;
    g.rect(wdX, wdY, wdW, wdH);
    g.fill(0x8b6914);
    g.stroke({ width: 2, color: 0x654321 });
    // Double doors
    g.moveTo(wdX + wdW / 2, wdY + PX * 2);
    g.lineTo(wdX + wdW / 2, wdY + wdH - PX * 2);
    g.stroke({ width: 2, color: 0x654321 });
    // Handles
    g.circle(wdX + wdW / 2 - PX * 3, wdY + wdH / 2, PX * 1.5);
    g.fill(0xdaa520);
    g.circle(wdX + wdW / 2 + PX * 3, wdY + wdH / 2, PX * 1.5);
    g.fill(0xdaa520);

    // ── Desk with computer ──
    const dkX = ox + PX * 8;
    const dkY = oy + wallH + T * 3;
    const dkW = T * 2.5;
    const dkH = T * 1.2;
    // Desk
    g.rect(dkX, dkY, dkW, dkH);
    g.fill(0xa0522d);
    g.stroke({ width: 2, color: 0x5c3a1e });
    // Desk legs
    g.rect(dkX + PX * 2, dkY + dkH, PX * 3, T * 0.6);
    g.fill(0x8b4513);
    g.rect(dkX + dkW - PX * 5, dkY + dkH, PX * 3, T * 0.6);
    g.fill(0x8b4513);
    // Monitor
    g.rect(dkX + PX * 8, dkY - T * 0.8, T * 1.4, T * 0.8);
    g.fill(0x333333);
    g.stroke({ width: 2, color: 0x222222 });
    // Screen
    g.rect(dkX + PX * 10, dkY - T * 0.8 + PX * 2, T * 1.4 - PX * 4, T * 0.8 - PX * 6);
    g.fill(0x2a4a6a);
    // Monitor stand
    g.rect(dkX + T * 0.6, dkY - PX * 2, PX * 8, PX * 4);
    g.fill(0x444444);
    // Keyboard
    g.roundRect(dkX + PX * 6, dkY + PX * 3, T * 1, PX * 6, PX);
    g.fill(0xd0d0d0);
    g.stroke({ width: 1, color: 0xaaaaaa });
    // Chair
    const chX = dkX + dkW / 2 - T * 0.4;
    const chY = dkY + dkH + T * 0.3;
    g.roundRect(chX, chY, T * 0.8, T * 0.6, PX * 2);
    g.fill(0x333333);
    g.stroke({ width: 1, color: 0x222222 });
    // Chair back
    g.roundRect(chX + PX * 2, chY - PX * 8, T * 0.8 - PX * 4, PX * 10, PX * 3);
    g.fill(0x333333);

    // ── Bedroom rug ──
    const brX = ox + rw / 2 - T * 0.8;
    const brY = oy + wallH + rh - wallH - T * 2;
    g.ellipse(brX + T * 0.8, brY + T * 0.6, T * 1, T * 0.8);
    g.fill(theme.bedroomRug);
    g.ellipse(brX + T * 0.8, brY + T * 0.6, T * 0.7, T * 0.5);
    g.stroke({ width: 1.5, color: theme.rugAccent, alpha: 0.5 });

    // ── Mirror on back wall ──
    const mrX = ox + rw - T * 1.5;
    const mrY = oy + PX * 6;
    g.roundRect(mrX, mrY, T * 0.8, T * 1.2, PX * 2);
    g.fill(0x87ceeb);
    g.fill({ color: 0xffffff, alpha: 0.2 });
    g.roundRect(mrX, mrY, T * 0.8, T * 1.2, PX * 2);
    g.stroke({ width: 2, color: 0xdaa520 });
  }

  private renderUI(): void {
    if (!this.agent) return;
    const a = this.agent;
    const dotColor = colorHex(STATUS_COLORS[a.status] ?? STATUS_COLORS.offline);
    const elapsed = this.formatElapsed(a.since);

    const statusEmoji: Record<string, string> = {
      idle: "\uD83D\uDFE2",
      working: "\uD83D\uDFE1",
      sleeping: "\uD83D\uDFE3",
      socializing: "\uD83D\uDFE0",
      offline: "\u26AB",
    };

    let cronHtml = "";
    if (this.cronJobs.length > 0) {
      cronHtml = `
        <div style="margin-left:16px;">
          <div style="color:#999;margin-bottom:4px;">Tasks:</div>
          ${this.cronJobs
            .map(
              (j) => `
            <button class="house-trigger-btn" data-job="${j.id}" style="
              background:rgba(255,255,255,0.1);border:1px solid rgba(255,255,255,0.2);
              border-radius:3px;padding:4px 8px;color:#fff;cursor:pointer;
              font-family:'Press Start 2P',monospace;font-size:7px;margin:2px 0;display:block;
            ">${j.name}</button>
          `,
            )
            .join("")}
        </div>
      `;
    }

    this.uiEl.innerHTML = `
      <div style="
        background:rgba(0,0,0,0.85);padding:14px 20px;
        display:flex;align-items:center;gap:16px;flex-wrap:wrap;
        border-top:2px solid rgba(255,255,255,0.2);
      ">
        <button id="house-back" style="
          background:rgba(255,255,255,0.15);border:none;border-radius:4px;
          padding:6px 10px;color:#fff;cursor:pointer;
          font-family:'Press Start 2P',monospace;font-size:9px;
        ">< Back</button>

        <div style="display:flex;align-items:center;gap:6px;">
          <span style="width:10px;height:10px;border-radius:50%;background:${dotColor};display:inline-block;"></span>
          <span style="color:#fbbf24;font-size:11px;">${a.name}</span>
          <span>${statusEmoji[a.status] ?? ""} ${a.status}</span>
        </div>

        ${a.detail ? `<div style="color:#aaa;">${a.detail}</div>` : ""}
        <div style="color:#666;font-size:8px;">${elapsed}</div>

        <div style="margin-left:auto;display:flex;gap:8px;">
          <button id="house-msg" style="
            background:#fbbf24;color:#000;border:none;border-radius:4px;
            padding:6px 10px;cursor:pointer;
            font-family:'Press Start 2P',monospace;font-size:8px;
          ">Message</button>
          <button id="house-toggle" style="
            background:${a.status === "offline" ? "#4ade80" : "#ef4444"};
            color:#fff;border:none;border-radius:4px;
            padding:6px 10px;cursor:pointer;
            font-family:'Press Start 2P',monospace;font-size:8px;
          ">${a.status === "offline" ? "Resume" : "Pause"}</button>
        </div>

        ${cronHtml}
      </div>
    `;

    // Wire buttons
    this.uiEl.querySelector("#house-back")!.addEventListener("click", () => {
      this.hide();
      this.onBack?.();
    });

    this.uiEl.querySelector("#house-msg")!.addEventListener("click", () => {
      // Dispatch a custom event that main.ts can listen to
      window.dispatchEvent(new CustomEvent("pixeltown:open-message", { detail: { agentId: a.id, agentName: a.name } }));
    });

    this.uiEl.querySelector("#house-toggle")!.addEventListener("click", () => {
      this.sendFn({
        type: "toggle_agent",
        agent: a.id,
        enabled: a.status === "offline",
      });
    });

    for (const btn of this.uiEl.querySelectorAll(".house-trigger-btn")) {
      btn.addEventListener("click", () => {
        this.sendFn({
          type: "trigger_task",
          agent: a.id,
          job_id: (btn as HTMLElement).dataset.job!,
        });
      });
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
