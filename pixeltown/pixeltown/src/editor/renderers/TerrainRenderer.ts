import { Graphics } from "pixi.js";
import { SCALED_TILE, MAP_COLS, MAP_ROWS } from "@/config";

/**
 * Seeded pseudo-random number generator (LCG).
 * Deterministic: same seed always produces the same sequence.
 */
function createRng(seed: number): () => number {
  let state = seed;
  return () => {
    state = (state * 1664525 + 1013904223) & 0x7fffffff;
    return state / 0x7fffffff;
  };
}

/** Terrain type enum — values stored in the terrain grid. */
export const TERRAIN_TYPES = {
  GRASS: 0,
  DIRT: 1,
  STONE: 2,
  WATER: 3,
  SAND: 4,
  PATH: 5,
} as const;

export type TerrainType = (typeof TERRAIN_TYPES)[keyof typeof TERRAIN_TYPES];

/** Color palette for each terrain type (used for palette previews). */
export const TERRAIN_COLORS: Record<TerrainType, number> = {
  [TERRAIN_TYPES.GRASS]: 0x7ec850,
  [TERRAIN_TYPES.DIRT]: 0x9b7b55,
  [TERRAIN_TYPES.STONE]: 0x808080,
  [TERRAIN_TYPES.WATER]: 0x4682b4,
  [TERRAIN_TYPES.SAND]: 0xe8d5a3,
  [TERRAIN_TYPES.PATH]: 0xc9b99a,
};

/** Grass shade variations — chosen via seeded random per tile. */
const GRASS_COLORS = [0x7ec850, 0x72b847, 0x85d155, 0x6aad3e, 0x7bc04d];

/** Cobblestone stone colors for path tiles. */
const PATH_STONE_COLORS = [0xbfb08e, 0xd4c5a9, 0xc4b594, 0xccbea0];
const PATH_BASE_COLOR = 0xc9b99a;

/**
 * Draw a single terrain tile at the given tile coordinates.
 * Uses a seeded random based on (tileX, tileY) for consistent variation.
 */
export function drawTerrainTile(
  g: Graphics,
  tileX: number,
  tileY: number,
  terrainType: number,
): void {
  const PX = SCALED_TILE / 16;
  const x = tileX * SCALED_TILE;
  const y = tileY * SCALED_TILE;

  // Seeded random from tile coords for consistent per-tile variation
  const tileSeed = (tileX * 73856093 + tileY * 19349663) & 0x7fffffff;
  const rand = createRng(tileSeed);

  switch (terrainType) {
    case TERRAIN_TYPES.GRASS: {
      const color = GRASS_COLORS[Math.floor(rand() * GRASS_COLORS.length)];
      g.rect(x, y, SCALED_TILE, SCALED_TILE);
      g.fill(color);
      break;
    }

    case TERRAIN_TYPES.DIRT: {
      g.rect(x, y, SCALED_TILE, SCALED_TILE);
      g.fill(0x9b7b55);
      // Slight variation specks
      for (let i = 0; i < 4; i++) {
        const sx = x + rand() * SCALED_TILE;
        const sy = y + rand() * SCALED_TILE;
        g.circle(sx, sy, PX * 0.8);
        g.fill({ color: 0x8b6b45, alpha: 0.5 });
      }
      break;
    }

    case TERRAIN_TYPES.STONE: {
      g.rect(x, y, SCALED_TILE, SCALED_TILE);
      g.fill(0x808080);
      // Stone cracks
      for (let i = 0; i < 2; i++) {
        const cx = x + PX * 2 + rand() * (SCALED_TILE - PX * 4);
        const cy = y + PX * 2 + rand() * (SCALED_TILE - PX * 4);
        g.moveTo(cx, cy);
        g.lineTo(cx + (rand() - 0.5) * PX * 6, cy + (rand() - 0.5) * PX * 6);
        g.stroke({ width: 1, color: 0x606060, alpha: 0.5 });
      }
      break;
    }

    case TERRAIN_TYPES.WATER: {
      g.rect(x, y, SCALED_TILE, SCALED_TILE);
      g.fill(0x4682b4);
      // Water shine
      g.ellipse(x + SCALED_TILE * 0.4, y + SCALED_TILE * 0.35, PX * 3, PX * 1.5);
      g.fill({ color: 0x87ceeb, alpha: 0.4 });
      break;
    }

    case TERRAIN_TYPES.SAND: {
      g.rect(x, y, SCALED_TILE, SCALED_TILE);
      g.fill(0xe8d5a3);
      // Sand grain dots
      for (let i = 0; i < 3; i++) {
        const sx = x + rand() * SCALED_TILE;
        const sy = y + rand() * SCALED_TILE;
        g.circle(sx, sy, PX * 0.5);
        g.fill({ color: 0xd4c593, alpha: 0.5 });
      }
      break;
    }

    case TERRAIN_TYPES.PATH: {
      // Cobblestone path — extracted from TownScene.drawGround()
      g.rect(x, y, SCALED_TILE, SCALED_TILE);
      g.fill(PATH_BASE_COLOR);
      // Cobblestone pattern: 3x3 grid of rounded stones
      for (let i = 0; i < 3; i++) {
        for (let j = 0; j < 3; j++) {
          const stoneX = x + PX * 1 + i * PX * 5;
          const stoneY = y + PX * 1 + j * PX * 5;
          const sc = PATH_STONE_COLORS[Math.floor(rand() * PATH_STONE_COLORS.length)];
          g.roundRect(stoneX, stoneY, PX * 4, PX * 4, PX);
          g.fill(sc);
          g.roundRect(stoneX, stoneY, PX * 4, PX * 4, PX);
          g.stroke({ width: 0.5, color: 0xa89070, alpha: 0.4 });
        }
      }
      break;
    }

    default: {
      // Unknown terrain — fallback to grass
      const fallbackColor = GRASS_COLORS[Math.floor(rand() * GRASS_COLORS.length)];
      g.rect(x, y, SCALED_TILE, SCALED_TILE);
      g.fill(fallbackColor);
      break;
    }
  }
}

/**
 * Render a full terrain grid. Each cell value is a terrain type number.
 * Grid is indexed as terrain[row][col] (i.e. terrain[tileY][tileX]).
 */
export function renderTerrainGrid(g: Graphics, terrain: number[][]): void {
  const rows = terrain.length;
  for (let ty = 0; ty < rows; ty++) {
    const cols = terrain[ty].length;
    for (let tx = 0; tx < cols; tx++) {
      drawTerrainTile(g, tx, ty, terrain[ty][tx]);
    }
  }
}
