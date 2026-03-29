import { Container, Graphics, Text, Sprite, Texture } from "pixi.js";
import { SCALED_TILE, STATUS_COLORS, IDLE_CONFIG } from "@/config";
import type { AgentStatus } from "@/net/Protocol";
import { getSheetForAgent, type SpriteSheet } from "@/sprites/SpriteConfig";
import { loadSheet } from "@/sprites/SpriteLoader";

type Direction = "up" | "down" | "left" | "right";

interface Point {
  x: number;
  y: number;
}

const PX = SCALED_TILE / 16;
const DEFAULT_ANIM_SPEED = 150; // ms per frame

/**
 * Agent entity — sprite-based pixel character with walk/idle animations.
 */
export class Agent {
  readonly id: string;
  readonly name: string;
  readonly container: Container;

  tileX: number;
  tileY: number;

  status: AgentStatus = "idle";
  detail = "";
  since = Date.now();

  private path: Point[] = [];
  private moving = false;
  private direction: Direction = "down";
  private moveSpeed = 1;

  private sprite: Sprite;
  private shadow: Graphics;
  private statusDot: Graphics;
  private nameLabel: Text;
  private bubble: Container | null = null;

  // Sprite / animation
  private sheetConfig: SpriteSheet;
  private frameTextures: Texture[] = [];
  private textureReady = false;
  private animKey = "idle_down";
  private animFrame = 0;
  private animTimer = 0;
  private lastTime = performance.now();

  constructor(id: string, name: string, tileX: number, tileY: number, _color?: number) {
    this.id = id;
    this.name = name;
    this.tileX = tileX;
    this.tileY = tileY;

    // Resolve sprite config for this agent
    this.sheetConfig = getSheetForAgent(id);

    this.container = new Container();
    this.container.x = tileX * SCALED_TILE;
    this.container.y = tileY * SCALED_TILE;

    // Shadow
    this.shadow = new Graphics();
    this.shadow.ellipse(SCALED_TILE / 2, SCALED_TILE - PX, PX * 6, PX * 2);
    this.shadow.fill({ color: 0x000000, alpha: 0.2 });
    this.container.addChild(this.shadow);

    // Sprite — render at 1.5x tile size so the small character fills the tile
    const spriteSize = SCALED_TILE * 1.5;
    const offset = (spriteSize - SCALED_TILE) / 2;
    this.sprite = new Sprite();
    this.sprite.width = spriteSize;
    this.sprite.height = spriteSize;
    this.sprite.x = -offset;
    this.sprite.y = -offset - PX * 2;
    this.container.addChild(this.sprite);

    // Load textures
    const cached = loadSheet(this.sheetConfig);
    if (cached.ready) {
      this.frameTextures = cached.textures;
      this.textureReady = true;
      this.applyTexture();
    } else {
      cached.promise.then(() => {
        this.frameTextures = cached.textures;
        this.textureReady = true;
        this.applyTexture();
      });
    }

    // Status dot
    this.statusDot = new Graphics();
    this.drawStatusDot();
    this.container.addChild(this.statusDot);

    // Name label
    this.nameLabel = new Text({
      text: name,
      style: {
        fontFamily: '"Press Start 2P", monospace',
        fontSize: 7,
        fill: 0xffffff,
        align: "center",
        stroke: { color: 0x000000, width: 2 },
      },
    });
    this.nameLabel.anchor.set(0.5, 0);
    this.nameLabel.x = SCALED_TILE / 2;
    this.nameLabel.y = SCALED_TILE + PX * 4;
    this.container.addChild(this.nameLabel);

    // Interactive
    this.container.eventMode = "static";
    this.container.cursor = "pointer";
  }

  private applyTexture(): void {
    const frames = this.sheetConfig.anims[this.animKey as keyof typeof this.sheetConfig.anims];
    if (frames && this.frameTextures[frames[0]]) {
      this.sprite.texture = this.frameTextures[frames[0]];
    }
  }

  setStatus(status: AgentStatus, detail: string, since: number): void {
    this.status = status;
    this.detail = detail;
    this.since = since;
    this.drawStatusDot();
    this.updateBubble();
  }

  setPath(path: Point[]): void {
    this.path = path.slice(1);
    this.moving = this.path.length > 0;
  }

  update(): boolean {
    const now = performance.now();
    const dt = now - this.lastTime;
    this.lastTime = now;

    // Advance sprite animation
    if (this.textureReady) {
      const speed = this.sheetConfig.animSpeed ?? DEFAULT_ANIM_SPEED;
      this.animTimer += dt;
      if (this.animTimer >= speed) {
        this.animTimer -= speed;
        const frames = this.sheetConfig.anims[this.animKey as keyof typeof this.sheetConfig.anims];
        if (frames && frames.length > 1) {
          this.animFrame = (this.animFrame + 1) % frames.length;
          this.sprite.texture = this.frameTextures[frames[this.animFrame]];
        }
      }
    }

    if (!this.moving || this.path.length === 0) {
      const idleKey = `idle_${this.direction}`;
      if (this.animKey !== idleKey) {
        this.setAnim(idleKey);
      }
      return false;
    }

    const target = this.path[0];
    const targetX = target.x * SCALED_TILE;
    const targetY = target.y * SCALED_TILE;

    const dx = targetX - this.container.x;
    const dy = targetY - this.container.y;
    const dist = Math.sqrt(dx * dx + dy * dy);

    if (dist < this.moveSpeed) {
      this.container.x = targetX;
      this.container.y = targetY;
      this.tileX = target.x;
      this.tileY = target.y;
      this.path.shift();
      if (this.path.length === 0) {
        this.moving = false;
        this.setAnim(`idle_${this.direction}`);
      }
      return true;
    }

    const vx = (dx / dist) * this.moveSpeed;
    const vy = (dy / dist) * this.moveSpeed;
    this.container.x += vx;
    this.container.y += vy;

    const newDir = Math.abs(dx) > Math.abs(dy)
      ? (dx > 0 ? "right" : "left")
      : (dy > 0 ? "down" : "up");
    if (newDir !== this.direction) {
      this.direction = newDir;
    }

    const walkKey = `walk_${this.direction}`;
    if (this.animKey !== walkKey) {
      this.setAnim(walkKey);
    }

    return true;
  }

  checkSleepTime(): boolean {
    const hour = new Date().getHours();
    return hour >= IDLE_CONFIG.sleepAfterHour || hour < 6;
  }

  isMoving(): boolean {
    return this.moving;
  }

  private setAnim(key: string): void {
    if (this.animKey === key) return;
    this.animKey = key;
    this.animFrame = 0;
    this.animTimer = 0;
    if (this.textureReady) {
      const frames = this.sheetConfig.anims[key as keyof typeof this.sheetConfig.anims];
      if (frames && this.frameTextures[frames[0]]) {
        this.sprite.texture = this.frameTextures[frames[0]];
      }
    }
  }

  private drawStatusDot(): void {
    this.statusDot.clear();
    const dotColor = STATUS_COLORS[this.status] ?? STATUS_COLORS.offline;
    const x = SCALED_TILE - PX * 2;
    const y = -PX * 6;
    this.statusDot.circle(x, y, PX * 3);
    this.statusDot.fill({ color: dotColor, alpha: 0.3 });
    this.statusDot.circle(x, y, PX * 2);
    this.statusDot.fill(dotColor);
    this.statusDot.circle(x, y, PX * 2);
    this.statusDot.stroke({ width: 1, color: 0x000000, alpha: 0.5 });
  }

  private updateBubble(): void {
    if (this.bubble) {
      this.container.removeChild(this.bubble);
      this.bubble = null;
    }

    let emoji = "";
    if (this.status === "working") emoji = "\u26A1";
    else if (this.status === "sleeping") emoji = "\uD83D\uDCA4";
    else if (this.status === "socializing") emoji = "\uD83D\uDCAC";
    else return;

    this.bubble = new Container();

    const bg = new Graphics();
    const bx = SCALED_TILE / 2;
    const by = -PX * 14;
    bg.roundRect(bx - PX * 6, by - PX * 5, PX * 12, PX * 10, PX * 2);
    bg.fill({ color: 0xffffff, alpha: 0.9 });
    bg.roundRect(bx - PX * 6, by - PX * 5, PX * 12, PX * 10, PX * 2);
    bg.stroke({ width: 1, color: 0x000000, alpha: 0.3 });
    bg.moveTo(bx - PX * 2, by + PX * 5);
    bg.lineTo(bx, by + PX * 8);
    bg.lineTo(bx + PX * 2, by + PX * 5);
    bg.fill({ color: 0xffffff, alpha: 0.9 });
    this.bubble.addChild(bg);

    const bubbleText = new Text({
      text: emoji,
      style: { fontSize: 12 },
    });
    bubbleText.anchor.set(0.5, 0.5);
    bubbleText.x = bx;
    bubbleText.y = by;
    this.bubble.addChild(bubbleText);
    this.container.addChild(this.bubble);
  }
}
