/** Shared types for the PixelTown Resource Editor. */

// ---------------------------------------------------------------------------
// Terrain
// ---------------------------------------------------------------------------

export const TerrainType = {
  grass: 0,
  dirt: 1,
  stone: 2,
  water: 3,
  sand: 4,
  path: 5,
} as const;

export type TerrainType = (typeof TerrainType)[keyof typeof TerrainType];

export const TERRAIN_NAMES: Record<TerrainType, string> = {
  [TerrainType.grass]: "grass",
  [TerrainType.dirt]: "dirt",
  [TerrainType.stone]: "stone",
  [TerrainType.water]: "water",
  [TerrainType.sand]: "sand",
  [TerrainType.path]: "path",
};

export const TERRAIN_COLORS: Record<TerrainType, number> = {
  [TerrainType.grass]: 0x4ade80,
  [TerrainType.dirt]: 0xb5651d,
  [TerrainType.stone]: 0x888888,
  [TerrainType.water]: 0x3b82f6,
  [TerrainType.sand]: 0xf5deb3,
  [TerrainType.path]: 0xd2b48c,
};

// ---------------------------------------------------------------------------
// Buildings
// ---------------------------------------------------------------------------

export interface BuildingDef {
  id: string;
  type: string;
  x: number;
  y: number;
  owner?: string;
  variant?: string;
}

// ---------------------------------------------------------------------------
// Decorations
// ---------------------------------------------------------------------------

export type DecorationType =
  | "tree_oak"
  | "tree_pine"
  | "bush"
  | "flower"
  | "rock"
  | "fence_h"
  | "fence_v"
  | "mushroom"
  | "bench";

export interface DecorationDef {
  type: DecorationType;
  x: number;
  y: number;
  variant?: string;
}

// ---------------------------------------------------------------------------
// Town Map
// ---------------------------------------------------------------------------

export interface TownMapConfig {
  terrain: number[][];
  buildings: BuildingDef[];
  decorations: DecorationDef[];
}

// ---------------------------------------------------------------------------
// Interior / Room layouts
// ---------------------------------------------------------------------------

export interface FurniturePlacement {
  type: string;
  x: number;
  y: number;
  rotation?: number;
}

export interface DoorDef {
  x: number;
  y: number;
  targetRoom?: string;
  targetX?: number;
  targetY?: number;
}

export interface Room {
  id: string;
  width: number;
  height: number;
  floor: number[][];
  walls: number[][];
  furniture: FurniturePlacement[];
  doors: DoorDef[];
}

export interface RoomLayout {
  rooms: Room[];
}

export interface InteriorConfig {
  layouts: Record<string, RoomLayout>;
}

// ---------------------------------------------------------------------------
// Characters
// ---------------------------------------------------------------------------

export interface CharacterConfig {
  agents: Record<
    string,
    {
      sheet: string;
      color?: number;
    }
  >;
  defaultSheet: string;
}

// ---------------------------------------------------------------------------
// Combined editor config (all tabs)
// ---------------------------------------------------------------------------

export interface EditorConfig {
  townMap: TownMapConfig;
  interior: InteriorConfig;
  characters: CharacterConfig;
}
