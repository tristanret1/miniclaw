/** Global constants for Pixel Town. */

export const TILE_SIZE = 16;
export const SCALE = 3; // render at 3x for crisp pixels
export const SCALED_TILE = TILE_SIZE * SCALE;

export const FRAME_RATE = 60;

/** Map dimensions in tiles. */
export const MAP_COLS = 40;
export const MAP_ROWS = 28;

/** Agent state colors (for status dots). */
export const STATUS_COLORS: Record<string, number> = {
  idle: 0x4ade80, // green
  working: 0xfbbf24, // amber
  sleeping: 0x818cf8, // indigo
  socializing: 0xf472b6, // pink
  offline: 0x6b7280, // gray
};

/** Day/night cycle phase boundaries (hours, 24h format). */
export const DAY_PHASES = {
  sunrise: { start: 6, end: 8 },
  daytime: { start: 8, end: 17 },
  sunset: { start: 17, end: 19 },
  night: { start: 19, end: 6 },
} as const;

/** Idle behavior weights (must sum to 1.0). */
export const IDLE_WEIGHTS = {
  wander: 0.3,
  goHome: 0.2,
  visitCottage: 0.15,
  sitBench: 0.1,
  lookFlowers: 0.1,
  goPlaza: 0.15,
} as const;

/** Default idle behavior config. */
export const IDLE_CONFIG = {
  wanderIntervalMin: 2_000, // ms
  wanderIntervalMax: 6_000,
  socialChance: 0.3,
  sleepAfterHour: 23,
} as const;

/** WebSocket reconnect config. */
export const WS_RECONNECT_DELAY = 2_000; // ms
export const WS_MAX_RECONNECT_DELAY = 30_000;
