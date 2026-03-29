import { DAY_PHASES } from "@/config";
import { ColorMatrixFilter } from "pixi.js";

export type DayPhase = "sunrise" | "daytime" | "sunset" | "night";

/** Determines current day phase from system clock. */
export function getCurrentPhase(): DayPhase {
  const hour = new Date().getHours() + new Date().getMinutes() / 60;
  if (hour >= DAY_PHASES.sunrise.start && hour < DAY_PHASES.sunrise.end) return "sunrise";
  if (hour >= DAY_PHASES.daytime.start && hour < DAY_PHASES.daytime.end) return "daytime";
  if (hour >= DAY_PHASES.sunset.start && hour < DAY_PHASES.sunset.end) return "sunset";
  return "night";
}

/** Progress within the current phase (0.0 - 1.0). */
export function getPhaseProgress(): number {
  const hour = new Date().getHours() + new Date().getMinutes() / 60;
  const phase = getCurrentPhase();
  const bounds = DAY_PHASES[phase];
  const start = bounds.start;
  const end = bounds.end > bounds.start ? bounds.end : bounds.end + 24;
  const current = hour >= start ? hour : hour + 24;
  return Math.min(1, Math.max(0, (current - start) / (end - start)));
}

/**
 * Day/night cycle system. Applies a ColorMatrixFilter to the root container.
 * Updates once per minute (not per frame).
 */
export class DayNightSystem {
  private filter: ColorMatrixFilter;
  private lastPhase: DayPhase | null = null;
  private updateInterval: ReturnType<typeof setInterval> | null = null;

  constructor() {
    this.filter = new ColorMatrixFilter();
  }

  getFilter(): ColorMatrixFilter {
    return this.filter;
  }

  start(): void {
    this.update();
    this.updateInterval = setInterval(() => this.update(), 60_000); // once per minute
  }

  stop(): void {
    if (this.updateInterval) {
      clearInterval(this.updateInterval);
      this.updateInterval = null;
    }
  }

  update(): void {
    const phase = getCurrentPhase();
    const progress = getPhaseProgress();

    if (phase === this.lastPhase) return;
    this.lastPhase = phase;

    // Reset filter
    this.filter.reset();

    switch (phase) {
      case "sunrise":
        // Warm orange tint fading out
        this.filter.saturate(0.2 * (1 - progress), true);
        this.filter.brightness(0.85 + 0.15 * progress, true);
        break;
      case "daytime":
        // Normal brightness — no filter adjustment needed
        break;
      case "sunset":
        // Warm gold → dark purple
        this.filter.saturate(-0.1 * progress, true);
        this.filter.brightness(1.0 - 0.2 * progress, true);
        break;
      case "night":
        // Deep blue filter
        this.filter.night(0.3, true);
        this.filter.brightness(0.6, true);
        break;
    }
  }
}
