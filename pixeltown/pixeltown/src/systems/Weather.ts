import { Container, Graphics, ColorMatrixFilter } from "pixi.js";
import type { WeatherType } from "@/net/Protocol";

interface Particle {
  x: number;
  y: number;
  vx: number;
  vy: number;
  life: number;
}

/** Simulated weather system with particle effects and color filters. */
export class WeatherSystem {
  private current: WeatherType = "sunny";
  private since: number = Date.now();
  private nextChange: number = Date.now() + this.randomInterval();

  // Particle rendering
  private particleContainer: Container;
  private particleGraphics: Graphics;
  private particles: Particle[] = [];
  private maxParticles = 100;
  private canvasW = 1440;
  private canvasH = 960;

  // Weather filter
  private filter: ColorMatrixFilter;
  private lightningTimer = 0;

  constructor() {
    this.particleContainer = new Container();
    this.particleGraphics = new Graphics();
    this.particleContainer.addChild(this.particleGraphics);
    this.filter = new ColorMatrixFilter();
  }

  getParticleContainer(): Container {
    return this.particleContainer;
  }

  getFilter(): ColorMatrixFilter {
    return this.filter;
  }

  getCurrentWeather(): WeatherType {
    return this.current;
  }

  getState() {
    return {
      type: this.current,
      since: this.since,
      next_change: this.nextChange,
    };
  }

  setCanvasSize(w: number, h: number): void {
    this.canvasW = w;
    this.canvasH = h;
  }

  /** Set weather from server init message. */
  setState(type: WeatherType, since: number, nextChange: number): void {
    this.current = type;
    this.since = since;
    this.nextChange = nextChange;
    this.applyFilter();
  }

  /** Check if it's time to transition (client-side simulation). */
  tick(): WeatherType | null {
    if (Date.now() < this.nextChange) return null;
    const prev = this.current;
    this.current = this.pickNext();
    this.since = Date.now();
    this.nextChange = Date.now() + this.randomInterval();
    if (prev !== this.current) {
      this.particles = [];
      this.applyFilter();
      return this.current;
    }
    return null;
  }

  /** Per-frame particle update. */
  updateParticles(): void {
    // Spawn new particles
    this.spawnParticles();

    // Update existing
    for (let i = this.particles.length - 1; i >= 0; i--) {
      const p = this.particles[i];
      p.x += p.vx;
      p.y += p.vy;
      p.life--;
      if (p.life <= 0 || p.y > this.canvasH || p.x < -20 || p.x > this.canvasW + 20) {
        this.particles.splice(i, 1);
      }
    }

    // Lightning flash for thunderstorm
    if (this.current === "thunderstorm") {
      this.lightningTimer--;
      if (this.lightningTimer <= 0 && Math.random() < 0.003) {
        this.lightningTimer = 5; // flash for 5 frames
      }
    }

    this.drawParticles();
  }

  private spawnParticles(): void {
    if (this.particles.length >= this.maxParticles) return;

    const spawnRate = this.getSpawnRate();
    for (let i = 0; i < spawnRate; i++) {
      if (this.particles.length >= this.maxParticles) break;
      const p = this.createParticle();
      if (p) this.particles.push(p);
    }
  }

  private getSpawnRate(): number {
    switch (this.current) {
      case "rainy": return 3;
      case "snowy": return 2;
      case "thunderstorm": return 5;
      case "sunny": return Math.random() < 0.02 ? 1 : 0; // rare birds
      default: return 0;
    }
  }

  private createParticle(): Particle | null {
    switch (this.current) {
      case "rainy":
        return {
          x: Math.random() * this.canvasW,
          y: -10,
          vx: -1 + Math.random() * 0.5,
          vy: 8 + Math.random() * 4,
          life: 120,
        };
      case "snowy":
        return {
          x: Math.random() * this.canvasW,
          y: -10,
          vx: Math.sin(Date.now() * 0.001 + Math.random() * 6) * 0.5,
          vy: 1 + Math.random() * 2,
          life: 300,
        };
      case "thunderstorm":
        return {
          x: Math.random() * this.canvasW,
          y: -10,
          vx: -2 + Math.random(),
          vy: 10 + Math.random() * 6,
          life: 80,
        };
      case "sunny":
        // Bird: moves horizontally
        return {
          x: -20,
          y: 20 + Math.random() * 100,
          vx: 1.5 + Math.random(),
          vy: Math.sin(Math.random() * 6) * 0.3,
          life: 600,
        };
      default:
        return null;
    }
  }

  private drawParticles(): void {
    this.particleGraphics.clear();

    for (const p of this.particles) {
      switch (this.current) {
        case "rainy":
          // Rain drop — thin line
          this.particleGraphics.moveTo(p.x, p.y);
          this.particleGraphics.lineTo(p.x + p.vx * 0.5, p.y + 6);
          this.particleGraphics.stroke({ width: 1.5, color: 0x6699cc, alpha: 0.6 });
          break;
        case "snowy":
          // Snowflake — small circle
          this.particleGraphics.circle(p.x, p.y, 2 + Math.random());
          this.particleGraphics.fill({ color: 0xffffff, alpha: 0.8 });
          break;
        case "thunderstorm":
          // Heavy rain — thicker line
          this.particleGraphics.moveTo(p.x, p.y);
          this.particleGraphics.lineTo(p.x + p.vx * 0.3, p.y + 8);
          this.particleGraphics.stroke({ width: 2, color: 0x5577aa, alpha: 0.7 });
          break;
        case "sunny":
          // Bird — simple V shape
          this.particleGraphics.moveTo(p.x - 4, p.y - 2);
          this.particleGraphics.lineTo(p.x, p.y);
          this.particleGraphics.lineTo(p.x + 4, p.y - 2);
          this.particleGraphics.stroke({ width: 1.5, color: 0x333333, alpha: 0.7 });
          break;
      }
    }

    // Lightning flash overlay
    if (this.current === "thunderstorm" && this.lightningTimer > 0) {
      this.particleGraphics.rect(0, 0, this.canvasW, this.canvasH);
      this.particleGraphics.fill({ color: 0xffffff, alpha: 0.3 });
    }
  }

  private applyFilter(): void {
    this.filter.reset();
    switch (this.current) {
      case "rainy":
        this.filter.saturate(-0.2, true);
        this.filter.brightness(0.85, true);
        break;
      case "thunderstorm":
        this.filter.saturate(-0.3, true);
        this.filter.brightness(0.7, true);
        break;
      case "snowy":
        this.filter.brightness(1.1, true);
        this.filter.saturate(-0.15, true);
        break;
      case "sunny":
      default:
        // Normal — no filter
        break;
    }
  }

  private pickNext(): WeatherType {
    const types: WeatherType[] = ["sunny", "rainy", "snowy", "thunderstorm"];
    const weights = [0.5, 0.25, 0.15, 0.1];
    const r = Math.random();
    let cumulative = 0;
    for (let i = 0; i < types.length; i++) {
      cumulative += weights[i];
      if (r < cumulative) return types[i];
    }
    return "sunny";
  }

  private randomInterval(): number {
    // 1-4 hours in ms
    return (1 + Math.random() * 3) * 3_600_000;
  }
}
