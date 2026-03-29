import { Container, Graphics, ColorMatrixFilter } from "pixi.js";
import type { SeasonType } from "@/net/Protocol";

/** Determine current season from calendar month. */
export function getCurrentSeason(): SeasonType {
  const month = new Date().getMonth(); // 0-indexed
  if (month >= 2 && month <= 4) return "spring";
  if (month >= 5 && month <= 7) return "summer";
  if (month >= 8 && month <= 10) return "autumn";
  return "winter";
}

interface SeasonParticle {
  x: number;
  y: number;
  vx: number;
  vy: number;
  rot: number;
  life: number;
}

/**
 * Season system — applies color tint and seasonal particles based on current month.
 * Checks once per hour since seasons change slowly.
 */
export class SeasonSystem {
  private current: SeasonType;
  private checkInterval: ReturnType<typeof setInterval> | null = null;
  private onChange: ((season: SeasonType) => void) | null = null;

  // Seasonal visual effects
  private filter: ColorMatrixFilter;
  private particleContainer: Container;
  private particleGraphics: Graphics;
  private particles: SeasonParticle[] = [];
  private canvasW = 1440;
  private canvasH = 960;

  constructor() {
    this.current = getCurrentSeason();
    this.filter = new ColorMatrixFilter();
    this.particleContainer = new Container();
    this.particleGraphics = new Graphics();
    this.particleContainer.addChild(this.particleGraphics);
    this.applySeasonFilter();
  }

  getCurrent(): SeasonType {
    return this.current;
  }

  getFilter(): ColorMatrixFilter {
    return this.filter;
  }

  getParticleContainer(): Container {
    return this.particleContainer;
  }

  /** Set from server init message. */
  setCurrent(season: SeasonType): void {
    this.current = season;
    this.applySeasonFilter();
  }

  setCanvasSize(w: number, h: number): void {
    this.canvasW = w;
    this.canvasH = h;
  }

  setOnChange(cb: (season: SeasonType) => void): void {
    this.onChange = cb;
  }

  start(): void {
    this.checkInterval = setInterval(() => {
      const now = getCurrentSeason();
      if (now !== this.current) {
        this.current = now;
        this.applySeasonFilter();
        this.onChange?.(now);
      }
    }, 3_600_000); // check every hour
  }

  stop(): void {
    if (this.checkInterval) {
      clearInterval(this.checkInterval);
      this.checkInterval = null;
    }
  }

  /** Per-frame particle update for seasonal effects. */
  updateParticles(): void {
    // Spawn seasonal particles
    if (this.current === "spring" && Math.random() < 0.05) {
      this.particles.push(this.createCherryBlossom());
    } else if (this.current === "autumn" && Math.random() < 0.04) {
      this.particles.push(this.createFallingLeaf());
    }

    // Update
    for (let i = this.particles.length - 1; i >= 0; i--) {
      const p = this.particles[i];
      p.x += p.vx + Math.sin(Date.now() * 0.002 + p.rot) * 0.3;
      p.y += p.vy;
      p.rot += 0.02;
      p.life--;
      if (p.life <= 0 || p.y > this.canvasH) {
        this.particles.splice(i, 1);
      }
    }

    this.drawParticles();
  }

  private createCherryBlossom(): SeasonParticle {
    return {
      x: Math.random() * this.canvasW,
      y: -10,
      vx: Math.random() * 0.5 - 0.25,
      vy: 0.5 + Math.random() * 1,
      rot: Math.random() * Math.PI * 2,
      life: 400,
    };
  }

  private createFallingLeaf(): SeasonParticle {
    return {
      x: Math.random() * this.canvasW,
      y: -10,
      vx: Math.random() - 0.5,
      vy: 0.8 + Math.random() * 1.2,
      rot: Math.random() * Math.PI * 2,
      life: 350,
    };
  }

  private drawParticles(): void {
    this.particleGraphics.clear();

    for (const p of this.particles) {
      if (this.current === "spring") {
        // Cherry blossom petal — small pink circle
        this.particleGraphics.circle(p.x, p.y, 3);
        this.particleGraphics.fill({ color: 0xffb7c5, alpha: 0.8 });
        this.particleGraphics.circle(p.x + 2, p.y + 1, 2);
        this.particleGraphics.fill({ color: 0xffc0cb, alpha: 0.6 });
      } else if (this.current === "autumn") {
        // Falling leaf — small colored shape
        const colors = [0xcc6633, 0xdd8833, 0xbb4422, 0xee9944];
        const color = colors[Math.floor(p.rot * 2) % colors.length];
        this.particleGraphics.ellipse(p.x, p.y, 4, 2.5);
        this.particleGraphics.fill({ color, alpha: 0.8 });
      }
    }
  }

  private applySeasonFilter(): void {
    this.filter.reset();
    switch (this.current) {
      case "spring":
        // Light, fresh green tint
        this.filter.saturate(0.15, true);
        this.filter.brightness(1.05, true);
        break;
      case "summer":
        // Vibrant, deep colors
        this.filter.saturate(0.2, true);
        break;
      case "autumn":
        // Warm orange/brown tint
        this.filter.saturate(-0.05, true);
        // Shift hue slightly warm
        this.filter.brightness(0.95, true);
        break;
      case "winter":
        // Cool blue tint, slightly desaturated
        this.filter.saturate(-0.2, true);
        this.filter.brightness(1.05, true);
        break;
    }
  }
}
