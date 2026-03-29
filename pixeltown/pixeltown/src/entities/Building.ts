import { Container, Graphics, Text } from "pixi.js";
import { SCALED_TILE } from "@/config";

export type BuildingType = "cottage" | "library" | "shop" | "plaza";

// pixel unit = SCALED_TILE / 16 for sub-tile detail
const PX = SCALED_TILE / 16;

/**
 * Building entity — Stardew Valley-style pixel art buildings.
 */
export class Building {
  readonly id: string;
  readonly type: BuildingType;
  readonly container: Container;

  tileX: number;
  tileY: number;
  readonly widthTiles: number;
  readonly heightTiles: number;
  ownerId?: string;

  private body: Graphics;
  private label: Text;
  private chimneySmoke = false;
  private windowGlow = false;
  private variant: number;

  constructor(
    id: string,
    type: BuildingType,
    tileX: number,
    tileY: number,
    ownerId?: string,
    variant?: number,
  ) {
    this.id = id;
    this.type = type;
    this.tileX = tileX;
    this.tileY = tileY;
    this.ownerId = ownerId;
    this.variant = variant ?? 0;

    const sizes: Record<BuildingType, [number, number]> = {
      cottage: [3, 3],
      library: [4, 3],
      shop: [3, 3],
      plaza: [5, 5],
    };
    [this.widthTiles, this.heightTiles] = sizes[type];

    this.container = new Container();
    this.container.x = tileX * SCALED_TILE;
    this.container.y = tileY * SCALED_TILE;

    this.body = new Graphics();
    this.drawBody();
    this.container.addChild(this.body);

    const displayName = ownerId ? `${ownerId.replace("agent-", "")}` : type;
    this.label = new Text({
      text: displayName,
      style: {
        fontFamily: '"Press Start 2P", monospace',
        fontSize: 7,
        fill: 0xffffff,
        align: "center",
        stroke: { color: 0x000000, width: 2 },
      },
    });
    this.label.anchor.set(0.5, 0);
    this.label.x = (this.widthTiles * SCALED_TILE) / 2;
    this.label.y = this.heightTiles * SCALED_TILE + 2;
    this.container.addChild(this.label);

    if (type === "cottage" || type === "plaza") {
      this.container.eventMode = "static";
      this.container.cursor = "pointer";
    }
  }

  setChimneySmoke(active: boolean): void {
    this.chimneySmoke = active;
    this.drawBody();
  }

  setWindowGlow(active: boolean): void {
    this.windowGlow = active;
    this.drawBody();
  }

  moveTo(tileX: number, tileY: number): void {
    this.tileX = tileX;
    this.tileY = tileY;
    this.container.x = tileX * SCALED_TILE;
    this.container.y = tileY * SCALED_TILE;
  }

  getDoorTile(): { x: number; y: number } {
    return {
      x: this.tileX + Math.floor(this.widthTiles / 2),
      y: this.tileY + this.heightTiles,
    };
  }

  private drawBody(): void {
    this.body.clear();
    switch (this.type) {
      case "cottage":
        this.drawCottage();
        break;
      case "library":
        this.drawLibrary();
        break;
      case "shop":
        this.drawShop();
        break;
      case "plaza":
        this.drawPlaza();
        break;
    }
  }

  private drawCottage(): void {
    const g = this.body;
    const w = this.widthTiles * SCALED_TILE;
    const h = this.heightTiles * SCALED_TILE;
    const wallTop = h * 0.32;

    // Per-variant palette
    const palettes = [
      { wall: 0xf5deb3, wallLine: 0xd4b896, roof: 0xb22222, roofDark: 0x8b1a1a, trim: 0x8b6914, door: 0x5c3a1e, chimney: 0xa0522d, flowers: [0xff6b6b, 0xffb347, 0xff69b4] },
      { wall: 0xd4e8d0, wallLine: 0xb8d4b2, roof: 0x3a7d44, roofDark: 0x2a5d34, trim: 0x5a4a3a, door: 0x6b4226, chimney: 0x8b8b8b, flowers: [0xeee8aa, 0xf0e68c, 0xfafad2] },
      { wall: 0xe0d4f0, wallLine: 0xc8b8e0, roof: 0x6a5acd, roofDark: 0x483d8b, trim: 0x8b7d6b, door: 0x4a3728, chimney: 0x9b7653, flowers: [0xda70d6, 0xba55d3, 0x9370db] },
    ];
    const p = palettes[this.variant % palettes.length];

    // Shadow
    g.rect(PX * 2, PX * 2 + wallTop, w, h * 0.68);
    g.fill({ color: 0x000000, alpha: 0.15 });

    // ── Walls ──
    g.rect(0, wallTop, w, h - wallTop);
    g.fill(p.wall);
    for (let i = 1; i < 6; i++) {
      const y = wallTop + (h - wallTop) * (i / 6);
      g.moveTo(PX, y);
      g.lineTo(w - PX, y);
      g.stroke({ width: 1, color: p.wallLine, alpha: 0.6 });
    }
    g.rect(0, wallTop, w, h - wallTop);
    g.stroke({ width: 2, color: p.trim });

    // ── Roof (variant shapes) ──
    const roofOverhang = PX * 4;
    if (this.variant === 1) {
      // Flat-ish gambrel roof
      g.moveTo(-roofOverhang, wallTop + PX);
      g.lineTo(PX * 6, wallTop - PX * 10);
      g.lineTo(w / 2, wallTop - PX * 16);
      g.lineTo(w - PX * 6, wallTop - PX * 10);
      g.lineTo(w + roofOverhang, wallTop + PX);
      g.closePath();
    } else if (this.variant === 2) {
      // Steeper roof with dormer window
      g.moveTo(-roofOverhang, wallTop + PX);
      g.lineTo(w / 2, -PX * 8);
      g.lineTo(w + roofOverhang, wallTop + PX);
      g.closePath();
    } else {
      // Standard triangular
      g.moveTo(-roofOverhang, wallTop + PX);
      g.lineTo(w / 2, -PX * 2);
      g.lineTo(w + roofOverhang, wallTop + PX);
      g.closePath();
    }
    g.fill(p.roof);
    g.stroke({ width: 2, color: p.roofDark });
    // Shingle lines
    for (let i = 1; i < 4; i++) {
      const progress = i / 4;
      const roofPeak = this.variant === 2 ? -PX * 8 : (this.variant === 1 ? wallTop - PX * 16 : -PX * 2);
      const y = roofPeak + (wallTop + PX * 3 - roofPeak) * progress;
      const halfW = (w / 2 + roofOverhang) * (1 - progress * 0.6);
      g.moveTo(w / 2 - halfW, y);
      g.lineTo(w / 2 + halfW, y);
      g.stroke({ width: 1, color: p.roofDark, alpha: 0.4 });
    }

    // Dormer window for variant 2
    if (this.variant === 2) {
      const dw = PX * 10;
      const dh = PX * 8;
      const dx = w / 2 - dw / 2;
      const dy = wallTop - PX * 10;
      g.rect(dx, dy, dw, dh);
      g.fill(p.wall);
      g.stroke({ width: 1, color: p.trim });
      // Mini roof
      g.moveTo(dx - PX * 2, dy);
      g.lineTo(dx + dw / 2, dy - PX * 6);
      g.lineTo(dx + dw + PX * 2, dy);
      g.closePath();
      g.fill(p.roof);
      g.stroke({ width: 1, color: p.roofDark });
      // Window in dormer
      this.drawWindow(g, dx + PX * 2, dy + PX, PX * 6, PX * 6);
    }

    // ── Chimney (different side per variant) ──
    const chimSide = this.variant === 1 ? 0.2 : 0.75;
    const chimX = w * chimSide;
    const chimW = PX * 6;
    const chimH = PX * 12;
    const chimTop = wallTop - chimH * 0.4;
    g.rect(chimX, chimTop, chimW, chimH);
    g.fill(p.chimney);
    g.rect(chimX, chimTop, chimW, chimH);
    g.stroke({ width: 1, color: 0x8b4513 });
    g.moveTo(chimX, chimTop + chimH * 0.33);
    g.lineTo(chimX + chimW, chimTop + chimH * 0.33);
    g.moveTo(chimX, chimTop + chimH * 0.66);
    g.lineTo(chimX + chimW, chimTop + chimH * 0.66);
    g.stroke({ width: 1, color: 0x8b4513 });
    if (this.chimneySmoke) {
      const smokeX = chimX + chimW / 2;
      for (let i = 0; i < 3; i++) {
        g.circle(smokeX + (i % 2 === 0 ? -PX : PX) * 2, chimTop - PX * (4 + i * 5), PX * (2 + i));
        g.fill({ color: 0xcccccc, alpha: 0.4 - i * 0.1 });
      }
    }

    // ── Door (variant styles) ──
    const doorW = PX * 10;
    const doorH = PX * 16;
    const doorX = w / 2 - doorW / 2;
    const doorY = h - doorH;
    if (this.variant === 1) {
      // Arched door
      g.roundRect(doorX, doorY, doorW, doorH, PX * 4);
      g.fill(p.door);
      g.roundRect(doorX, doorY, doorW, doorH, PX * 4);
      g.stroke({ width: 2, color: 0x3e2510 });
    } else {
      g.roundRect(doorX, doorY, doorW, doorH, 2);
      g.fill(p.door);
      g.roundRect(doorX, doorY, doorW, doorH, 2);
      g.stroke({ width: 2, color: 0x3e2510 });
    }
    g.rect(doorX - PX, doorY - PX, doorW + PX * 2, PX * 2);
    g.fill(p.trim);
    g.circle(doorX + doorW - PX * 3, doorY + doorH / 2, PX * 1.5);
    g.fill(0xdaa520);

    // ── Windows ──
    this.drawWindow(g, PX * 6, wallTop + PX * 8, PX * 12, PX * 10);
    this.drawWindow(g, w - PX * 18, wallTop + PX * 8, PX * 12, PX * 10);

    // ── Flower box ──
    const fbSide = this.variant === 2 ? w - PX * 19 : PX * 5;
    const fbY = wallTop + PX * 19;
    g.rect(fbSide, fbY, PX * 14, PX * 4);
    g.fill(0x8b4513);
    g.stroke({ width: 1, color: 0x654321 });
    for (let i = 0; i < 5; i++) {
      g.circle(fbSide + PX * 2 + i * PX * 2.5, fbY - PX * 1, PX * 1.5);
      g.fill(p.flowers[i % p.flowers.length]);
    }
    for (let i = 0; i < 5; i++) {
      g.moveTo(fbSide + PX * 2 + i * PX * 2.5, fbY);
      g.lineTo(fbSide + PX * 2 + i * PX * 2.5, fbY - PX * 1);
      g.stroke({ width: 1, color: 0x228b22 });
    }

    // ── Porch ──
    g.rect(doorX - PX * 3, h - PX * 2, doorW + PX * 6, PX * 4);
    g.fill(0xc9b99a);
    g.stroke({ width: 1, color: 0xa89070 });

    // ── Extra details per variant ──
    if (this.variant === 0) {
      // Mailbox
      g.rect(w - PX * 4, h - PX * 8, PX * 3, PX * 8);
      g.fill(0x654321);
      g.rect(w - PX * 6, h - PX * 12, PX * 7, PX * 5);
      g.fill(0x4169e1);
      g.stroke({ width: 1, color: 0x2c4ba0 });
    } else if (this.variant === 1) {
      // Fence posts
      for (let i = 0; i < 3; i++) {
        const fx = -PX * 4 + i * PX * 6;
        g.rect(fx, h - PX * 10, PX * 2, PX * 10);
        g.fill(0xf5f5dc);
        g.stroke({ width: 1, color: 0xd2b48c });
      }
      // Fence rail
      g.rect(-PX * 4, h - PX * 7, PX * 14, PX * 2);
      g.fill(0xf5f5dc);
    } else {
      // Lantern by door
      g.rect(doorX - PX * 6, doorY + PX * 2, PX * 2, PX * 6);
      g.fill(0x404040);
      g.circle(doorX - PX * 5, doorY + PX, PX * 3);
      g.fill(0xfff59d);
      g.stroke({ width: 1, color: 0xdaa520 });
    }
  }

  private drawLibrary(): void {
    const g = this.body;
    const w = this.widthTiles * SCALED_TILE;
    const h = this.heightTiles * SCALED_TILE;
    const wallTop = h * 0.28;

    // Shadow
    g.rect(PX * 2, PX * 2 + wallTop, w, h * 0.72);
    g.fill({ color: 0x000000, alpha: 0.15 });

    // ── Stone base ──
    g.rect(0, h - PX * 6, w, PX * 6);
    g.fill(0x808080);
    g.stroke({ width: 1, color: 0x606060 });

    // ── Walls (stone/brick) ──
    g.rect(0, wallTop, w, h - wallTop - PX * 6);
    g.fill(0xd2b48c);
    // Brick pattern
    for (let row = 0; row < 5; row++) {
      const y = wallTop + (h - wallTop - PX * 6) * (row / 5);
      g.moveTo(0, y);
      g.lineTo(w, y);
      g.stroke({ width: 1, color: 0xc4a882, alpha: 0.5 });
      for (let col = 0; col < 6; col++) {
        const offset = row % 2 === 0 ? 0 : w / 12;
        const x = offset + col * (w / 6);
        if (x > 0 && x < w) {
          g.moveTo(x, y);
          g.lineTo(x, y + (h - wallTop - PX * 6) / 5);
          g.stroke({ width: 1, color: 0xc4a882, alpha: 0.3 });
        }
      }
    }
    g.rect(0, wallTop, w, h - wallTop);
    g.stroke({ width: 2, color: 0x8b6914 });

    // ── Roof ──
    const roofOverhang = PX * 5;
    g.moveTo(-roofOverhang, wallTop + PX);
    g.lineTo(w / 2, -PX * 6);
    g.lineTo(w + roofOverhang, wallTop + PX);
    g.closePath();
    g.fill(0x4a6741); // dark green roof
    g.stroke({ width: 2, color: 0x3a5731 });

    // ── Arched windows ──
    const winW = PX * 10;
    const winH = PX * 14;
    for (let i = 0; i < 3; i++) {
      const x = PX * 8 + i * (w / 3 - PX);
      const y = wallTop + PX * 6;
      // Arch
      g.roundRect(x, y, winW, winH, PX * 3);
      g.fill(this.windowGlow ? 0xfff59d : 0x87ceeb);
      g.roundRect(x, y, winW, winH, PX * 3);
      g.stroke({ width: 2, color: 0x5c3a1e });
      // Cross bar
      g.moveTo(x + winW / 2, y + PX);
      g.lineTo(x + winW / 2, y + winH - PX);
      g.moveTo(x + PX, y + winH / 2);
      g.lineTo(x + winW - PX, y + winH / 2);
      g.stroke({ width: 1.5, color: 0x5c3a1e });
    }

    // ── Door ──
    const doorW = PX * 14;
    const doorH = PX * 18;
    const doorX = w / 2 - doorW / 2;
    g.roundRect(doorX, h - doorH, doorW, doorH, PX * 2);
    g.fill(0x654321);
    g.roundRect(doorX, h - doorH, doorW, doorH, PX * 2);
    g.stroke({ width: 2, color: 0x3e2510 });
    // Double door line
    g.moveTo(w / 2, h - doorH + PX * 2);
    g.lineTo(w / 2, h);
    g.stroke({ width: 2, color: 0x3e2510 });
    // Doorknobs
    g.circle(w / 2 - PX * 2, h - doorH / 2, PX * 1.5);
    g.circle(w / 2 + PX * 2, h - doorH / 2, PX * 1.5);
    g.fill(0xdaa520);

    // ── Sign ──
    g.rect(w / 2 - PX * 10, wallTop + PX * 2, PX * 20, PX * 5);
    g.fill(0x8b6914);
    g.stroke({ width: 1, color: 0x654321 });
  }

  private drawShop(): void {
    const g = this.body;
    const w = this.widthTiles * SCALED_TILE;
    const h = this.heightTiles * SCALED_TILE;
    const wallTop = h * 0.3;

    // Shadow
    g.rect(PX * 2, PX * 2 + wallTop, w, h * 0.7);
    g.fill({ color: 0x000000, alpha: 0.15 });

    // ── Walls ──
    g.rect(0, wallTop, w, h - wallTop);
    g.fill(0xe8d5b7);
    g.rect(0, wallTop, w, h - wallTop);
    g.stroke({ width: 2, color: 0x8b6914 });

    // ── Roof ──
    g.moveTo(-PX * 4, wallTop + PX);
    g.lineTo(w / 2, -PX * 2);
    g.lineTo(w + PX * 4, wallTop + PX);
    g.closePath();
    g.fill(0x4169e1); // blue roof
    g.stroke({ width: 2, color: 0x2c4ba0 });

    // ── Awning ──
    const awningY = wallTop + PX * 3;
    g.rect(-PX * 2, awningY, w + PX * 4, PX * 8);
    g.fill(0xe74c3c);
    g.stroke({ width: 1, color: 0xc0392b });
    // Awning stripes
    for (let i = 0; i < 8; i++) {
      if (i % 2 === 0) {
        const stripX = -PX * 2 + i * ((w + PX * 4) / 8);
        g.rect(stripX, awningY, (w + PX * 4) / 8, PX * 8);
        g.fill({ color: 0xffffff, alpha: 0.3 });
      }
    }
    // Awning scalloped bottom
    for (let i = 0; i < 6; i++) {
      const scX = -PX + i * (w / 5);
      g.moveTo(scX, awningY + PX * 8);
      g.quadraticCurveTo(scX + w / 10, awningY + PX * 11, scX + w / 5, awningY + PX * 8);
      g.fill({ color: 0xe74c3c, alpha: 0.8 });
    }

    // ── Display window ──
    const winX = PX * 4;
    const winY = awningY + PX * 10;
    const winW = w - PX * 8;
    const winH = PX * 14;
    g.rect(winX, winY, winW, winH);
    g.fill(0x87ceeb);
    g.rect(winX, winY, winW, winH);
    g.stroke({ width: 2, color: 0x5c3a1e });
    // Window display items (colored boxes = goods)
    const itemColors = [0xff6347, 0x32cd32, 0xffa500, 0x9370db];
    for (let i = 0; i < 4; i++) {
      g.rect(winX + PX * 3 + i * PX * 8, winY + winH - PX * 6, PX * 5, PX * 5);
      g.fill(itemColors[i]);
    }

    // ── Door ──
    const doorW = PX * 10;
    const doorH = PX * 16;
    const doorX = w / 2 - doorW / 2;
    g.roundRect(doorX, h - doorH, doorW, doorH, 2);
    g.fill(0x5c3a1e);
    g.stroke({ width: 2, color: 0x3e2510 });
    g.circle(doorX + doorW - PX * 3, h - doorH / 2, PX * 1.5);
    g.fill(0xdaa520);

    // ── Sign board ──
    g.rect(w / 2 - PX * 8, wallTop - PX * 3, PX * 16, PX * 6);
    g.fill(0xdeb887);
    g.stroke({ width: 1, color: 0x8b6914 });
  }

  private drawPlaza(): void {
    const g = this.body;
    const w = this.widthTiles * SCALED_TILE;
    const h = this.heightTiles * SCALED_TILE;

    // ── Stone tile ground ──
    g.rect(0, 0, w, h);
    g.fill(0xc9b99a);
    // Tile pattern
    for (let row = 0; row <= this.heightTiles; row++) {
      g.moveTo(0, row * SCALED_TILE);
      g.lineTo(w, row * SCALED_TILE);
      g.stroke({ width: 1, color: 0xb8a888, alpha: 0.6 });
    }
    for (let col = 0; col <= this.widthTiles; col++) {
      g.moveTo(col * SCALED_TILE, 0);
      g.lineTo(col * SCALED_TILE, h);
      g.stroke({ width: 1, color: 0xb8a888, alpha: 0.6 });
    }
    // Border
    g.rect(0, 0, w, h);
    g.stroke({ width: 2, color: 0x8b7355 });

    // ── Central fountain ──
    const cx = w / 2;
    const cy = h / 2;
    // Base
    g.circle(cx, cy, PX * 16);
    g.fill(0x808080);
    g.stroke({ width: 2, color: 0x606060 });
    // Water
    g.circle(cx, cy, PX * 13);
    g.fill(0x5f9ea0);
    // Pillar
    g.rect(cx - PX * 3, cy - PX * 12, PX * 6, PX * 14);
    g.fill(0x909090);
    g.stroke({ width: 1, color: 0x707070 });
    // Top bowl
    g.ellipse(cx, cy - PX * 12, PX * 8, PX * 3);
    g.fill(0x909090);
    g.stroke({ width: 1, color: 0x707070 });
    // Water spray dots
    for (let i = 0; i < 5; i++) {
      const angle = (i / 5) * Math.PI * 2;
      g.circle(cx + Math.cos(angle) * PX * 5, cy - PX * 14 + Math.sin(angle) * PX * 2, PX);
      g.fill({ color: 0x87ceeb, alpha: 0.7 });
    }

    // ── Benches ──
    this.drawBench(g, PX * 6, h - PX * 16);
    this.drawBench(g, w - PX * 22, h - PX * 16);

    // ── Flower beds (corners) ──
    const flowerColors = [0xff6b6b, 0xffb347, 0xff69b4, 0x9370db];
    const corners = [
      [PX * 4, PX * 4],
      [w - PX * 12, PX * 4],
      [PX * 4, h - PX * 12],
      [w - PX * 12, h - PX * 12],
    ];
    for (let c = 0; c < corners.length; c++) {
      const [fx, fy] = corners[c];
      g.rect(fx, fy, PX * 8, PX * 8);
      g.fill(0x5a3e28);
      for (let i = 0; i < 4; i++) {
        g.circle(fx + PX * 2 + (i % 2) * PX * 4, fy + PX * 2 + Math.floor(i / 2) * PX * 4, PX * 1.5);
        g.fill(flowerColors[(c + i) % 4]);
      }
      // Leaves
      for (let i = 0; i < 3; i++) {
        g.circle(fx + PX * 1 + i * PX * 3, fy + PX * 5, PX * 1.2);
        g.fill(0x228b22);
      }
    }

    // ── Lamp posts ──
    for (const lx of [PX * 4, w - PX * 6]) {
      g.rect(lx, cy - PX * 8, PX * 2, PX * 16);
      g.fill(0x404040);
      g.circle(lx + PX, cy - PX * 8, PX * 3);
      g.fill(0xfff59d);
      g.circle(lx + PX, cy - PX * 8, PX * 3);
      g.stroke({ width: 1, color: 0xdaa520 });
    }
  }

  private drawBench(g: Graphics, x: number, y: number): void {
    // Seat
    g.rect(x, y + PX * 2, PX * 16, PX * 4);
    g.fill(0x8b4513);
    g.stroke({ width: 1, color: 0x654321 });
    // Legs
    g.rect(x + PX, y + PX * 6, PX * 2, PX * 4);
    g.fill(0x654321);
    g.rect(x + PX * 13, y + PX * 6, PX * 2, PX * 4);
    g.fill(0x654321);
    // Back
    g.rect(x, y, PX * 16, PX * 3);
    g.fill(0x8b4513);
    g.stroke({ width: 1, color: 0x654321 });
  }

  private drawWindow(g: Graphics, x: number, y: number, w: number, h: number): void {
    // Window frame
    g.rect(x - PX, y - PX, w + PX * 2, h + PX * 2);
    g.fill(0x8b6914);
    // Glass
    g.rect(x, y, w, h);
    g.fill(this.windowGlow ? 0xfff59d : 0xadd8e6);
    // Cross bars
    g.moveTo(x + w / 2, y);
    g.lineTo(x + w / 2, y + h);
    g.moveTo(x, y + h / 2);
    g.lineTo(x + w, y + h / 2);
    g.stroke({ width: 1.5, color: 0x8b6914 });
    // Curtain hints
    g.moveTo(x + PX, y + PX);
    g.lineTo(x + PX * 3, y + h - PX);
    g.stroke({ width: 1, color: 0xffffff, alpha: 0.3 });
    g.moveTo(x + w - PX, y + PX);
    g.lineTo(x + w - PX * 3, y + h - PX);
    g.stroke({ width: 1, color: 0xffffff, alpha: 0.3 });
  }
}
