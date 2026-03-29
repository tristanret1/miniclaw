/**
 * Town Map Editor mode.
 * Handles terrain painting, building placement, decoration placement, and erasing.
 */

import { Container, Graphics } from "pixi.js";
import { SCALED_TILE, MAP_COLS, MAP_ROWS } from "@/config";
import { Building, BuildingType } from "@/entities/Building";
import { CommandHistory, EditorCommand } from "../CommandHistory";
import { EditorGrid } from "../EditorGrid";
import {
  TerrainType,
  TERRAIN_COLORS,
  DecorationType,
  TownMapConfig,
  BuildingDef,
  DecorationDef,
} from "../types";

// ---------------------------------------------------------------------------
// Tool types
// ---------------------------------------------------------------------------

export type TownTool = "paint" | "place" | "erase";

// ---------------------------------------------------------------------------
// Commands
// ---------------------------------------------------------------------------

export class PaintTerrainCommand implements EditorCommand {
  readonly description: string;
  private terrain: number[][];
  private cells: { col: number; row: number; oldType: number; newType: number }[];

  constructor(
    terrain: number[][],
    cells: { col: number; row: number; oldType: number; newType: number }[],
  ) {
    this.terrain = terrain;
    this.cells = cells;
    this.description = `Paint ${cells.length} terrain tile(s)`;
  }

  execute(): void {
    for (const c of this.cells) {
      this.terrain[c.row][c.col] = c.newType;
    }
  }

  undo(): void {
    for (const c of this.cells) {
      this.terrain[c.row][c.col] = c.oldType;
    }
  }
}

export class PlaceBuildingCommand implements EditorCommand {
  readonly description: string;
  private buildings: BuildingDef[];
  private def: BuildingDef;

  constructor(buildings: BuildingDef[], def: BuildingDef) {
    this.buildings = buildings;
    this.def = def;
    this.description = `Place building ${def.type} at (${def.x},${def.y})`;
  }

  execute(): void {
    this.buildings.push(this.def);
  }

  undo(): void {
    const idx = this.buildings.indexOf(this.def);
    if (idx >= 0) this.buildings.splice(idx, 1);
  }
}

export class PlaceDecorationCommand implements EditorCommand {
  readonly description: string;
  private decorations: DecorationDef[];
  private def: DecorationDef;

  constructor(decorations: DecorationDef[], def: DecorationDef) {
    this.decorations = decorations;
    this.def = def;
    this.description = `Place decoration ${def.type} at (${def.x},${def.y})`;
  }

  execute(): void {
    this.decorations.push(this.def);
  }

  undo(): void {
    const idx = this.decorations.indexOf(this.def);
    if (idx >= 0) this.decorations.splice(idx, 1);
  }
}

export class EraseCommand implements EditorCommand {
  readonly description: string;
  private buildings: BuildingDef[];
  private decorations: DecorationDef[];
  private removedBuilding: BuildingDef | null;
  private removedBuildingIndex: number;
  private removedDecoration: DecorationDef | null;
  private removedDecorationIndex: number;

  constructor(
    buildings: BuildingDef[],
    decorations: DecorationDef[],
    col: number,
    row: number,
  ) {
    this.buildings = buildings;
    this.decorations = decorations;
    this.removedBuilding = null;
    this.removedBuildingIndex = -1;
    this.removedDecoration = null;
    this.removedDecorationIndex = -1;

    // Find building at this tile (buildings occupy a rectangular area).
    const bSizes: Record<string, [number, number]> = {
      cottage: [3, 3],
      library: [4, 3],
      shop: [3, 3],
      plaza: [5, 5],
    };
    for (let i = buildings.length - 1; i >= 0; i--) {
      const b = buildings[i];
      const [bw, bh] = bSizes[b.type] ?? [1, 1];
      if (col >= b.x && col < b.x + bw && row >= b.y && row < b.y + bh) {
        this.removedBuilding = b;
        this.removedBuildingIndex = i;
        break;
      }
    }

    // Find decoration at this exact tile.
    if (!this.removedBuilding) {
      for (let i = decorations.length - 1; i >= 0; i--) {
        if (decorations[i].x === col && decorations[i].y === row) {
          this.removedDecoration = decorations[i];
          this.removedDecorationIndex = i;
          break;
        }
      }
    }

    const target = this.removedBuilding
      ? `building ${this.removedBuilding.type}`
      : this.removedDecoration
        ? `decoration ${this.removedDecoration.type}`
        : "nothing";
    this.description = `Erase ${target} at (${col},${row})`;
  }

  get hasTarget(): boolean {
    return this.removedBuilding !== null || this.removedDecoration !== null;
  }

  execute(): void {
    if (this.removedBuilding) {
      const idx = this.buildings.indexOf(this.removedBuilding);
      if (idx >= 0) this.buildings.splice(idx, 1);
    } else if (this.removedDecoration) {
      const idx = this.decorations.indexOf(this.removedDecoration);
      if (idx >= 0) this.decorations.splice(idx, 1);
    }
  }

  undo(): void {
    if (this.removedBuilding) {
      this.buildings.splice(this.removedBuildingIndex, 0, this.removedBuilding);
    } else if (this.removedDecoration) {
      this.decorations.splice(this.removedDecorationIndex, 0, this.removedDecoration);
    }
  }
}

// ---------------------------------------------------------------------------
// Decoration rendering helpers
// ---------------------------------------------------------------------------

const DECORATION_COLORS: Record<DecorationType, number> = {
  tree_oak: 0x228b22,
  tree_pine: 0x006400,
  bush: 0x32cd32,
  flower: 0xff69b4,
  rock: 0x808080,
  fence_h: 0xdeb887,
  fence_v: 0xdeb887,
  mushroom: 0xff6347,
  bench: 0x8b4513,
};

// ---------------------------------------------------------------------------
// TownMapEditor
// ---------------------------------------------------------------------------

export class TownMapEditor {
  private container: Container;
  private terrainLayer: Graphics;
  private buildingLayer: Container;
  private decorationLayer: Graphics;
  private commandHistory: CommandHistory | null = null;
  private parentContainer: Container | null = null;
  private grid: EditorGrid | null = null;

  private config: TownMapConfig;

  private activeTool: TownTool = "paint";
  private selectedCategory = "terrain";
  private selectedItemId = "grass";

  // Paint stroke state.
  private painting = false;
  private strokeCells: { col: number; row: number; oldType: number; newType: number }[] = [];
  private strokeVisited = new Set<string>();

  // Building instances for rendering.
  private buildingInstances: Map<BuildingDef, Building> = new Map();

  constructor(config: TownMapConfig) {
    this.config = config;

    this.container = new Container();
    this.container.label = "TownMapEditor";
    this.container.eventMode = "static";
    this.container.hitArea = {
      contains: (x: number, y: number) =>
        x >= 0 && y >= 0 && x < MAP_COLS * SCALED_TILE && y < MAP_ROWS * SCALED_TILE,
    };

    this.terrainLayer = new Graphics();
    this.terrainLayer.label = "TerrainLayer";
    this.container.addChild(this.terrainLayer);

    this.buildingLayer = new Container();
    this.buildingLayer.label = "BuildingLayer";
    this.container.addChild(this.buildingLayer);

    this.decorationLayer = new Graphics();
    this.decorationLayer.label = "DecorationLayer";
    this.container.addChild(this.decorationLayer);

    // Pointer events.
    this.container.on("pointerdown", this.onPointerDown, this);
    this.container.on("pointermove", this.onPointerMove, this);
    this.container.on("pointerup", this.onPointerUp, this);
    this.container.on("pointerupoutside", this.onPointerUp, this);
  }

  // -----------------------------------------------------------------------
  // Public API
  // -----------------------------------------------------------------------

  attach(parentContainer: Container, commandHistory: CommandHistory, grid: EditorGrid): void {
    this.parentContainer = parentContainer;
    this.commandHistory = commandHistory;
    this.grid = grid;
    // Insert below the grid overlay.
    const gridIdx = parentContainer.children.indexOf(grid.container);
    if (gridIdx >= 0) {
      parentContainer.addChildAt(this.container, gridIdx);
    } else {
      parentContainer.addChild(this.container);
    }
    this.render();
  }

  detach(): void {
    if (this.parentContainer && this.container.parent === this.parentContainer) {
      this.parentContainer.removeChild(this.container);
    }
    this.parentContainer = null;
    this.commandHistory = null;
    this.grid = null;
  }

  setTool(tool: TownTool): void {
    this.activeTool = tool;
  }

  getTool(): TownTool {
    return this.activeTool;
  }

  setSelectedItem(category: string, itemId: string): void {
    this.selectedCategory = category;
    this.selectedItemId = itemId;
    // Auto-switch tool based on category.
    if (category === "terrain") {
      this.activeTool = "paint";
    } else if (category === "building" || category === "decoration") {
      this.activeTool = "place";
    }
  }

  getConfig(): TownMapConfig {
    return this.config;
  }

  loadConfig(config: TownMapConfig): void {
    this.config = config;
    this.rebuildBuildingInstances();
    this.render();
  }

  /** Full redraw of all layers. */
  render(): void {
    this.renderTerrain();
    this.renderBuildings();
    this.renderDecorations();
  }

  // -----------------------------------------------------------------------
  // Pointer events
  // -----------------------------------------------------------------------

  private pixelToTile(e: { global: { x: number; y: number } }): { col: number; row: number } {
    const local = this.container.toLocal(e.global);
    const col = Math.floor(local.x / SCALED_TILE);
    const row = Math.floor(local.y / SCALED_TILE);
    return {
      col: Math.max(0, Math.min(col, MAP_COLS - 1)),
      row: Math.max(0, Math.min(row, MAP_ROWS - 1)),
    };
  }

  private onPointerDown(e: import("pixi.js").FederatedPointerEvent): void {
    const { col, row } = this.pixelToTile(e);

    if (this.activeTool === "paint" && this.selectedCategory === "terrain") {
      this.painting = true;
      this.strokeCells = [];
      this.strokeVisited.clear();
      this.paintTile(col, row);
    } else if (this.activeTool === "place") {
      this.placeItem(col, row);
    } else if (this.activeTool === "erase") {
      this.eraseAt(col, row);
    }
  }

  private onPointerMove(e: import("pixi.js").FederatedPointerEvent): void {
    if (this.painting && this.activeTool === "paint") {
      const { col, row } = this.pixelToTile(e);
      this.paintTile(col, row);
    }

    // Update grid hover.
    if (this.grid) {
      const { col, row } = this.pixelToTile(e);
      this.grid.setHover(col, row);
    }
  }

  private onPointerUp(_e: import("pixi.js").FederatedPointerEvent): void {
    if (this.painting && this.strokeCells.length > 0) {
      const cmd = new PaintTerrainCommand(this.config.terrain, [...this.strokeCells]);
      // Command already executed via paintTile; we push it as-is.
      // But CommandHistory.execute() calls execute() again, so we need to undo first.
      // Instead, we manually push: undo the live edits, then execute via history.
      for (const c of this.strokeCells) {
        this.config.terrain[c.row][c.col] = c.oldType;
      }
      this.commandHistory?.execute(cmd);
      this.renderTerrain();
    }
    this.painting = false;
    this.strokeCells = [];
    this.strokeVisited.clear();
  }

  // -----------------------------------------------------------------------
  // Tool actions
  // -----------------------------------------------------------------------

  private paintTile(col: number, row: number): void {
    const key = `${col},${row}`;
    if (this.strokeVisited.has(key)) return;
    this.strokeVisited.add(key);

    const terrainId = this.terrainNameToId(this.selectedItemId);
    const oldType = this.config.terrain[row][col];
    if (oldType === terrainId) return;

    this.strokeCells.push({ col, row, oldType, newType: terrainId });
    // Live preview: apply immediately.
    this.config.terrain[row][col] = terrainId;
    this.renderTerrain();
  }

  private placeItem(col: number, row: number): void {
    if (this.selectedCategory === "building") {
      const id = `bld_${Date.now()}_${Math.random().toString(36).slice(2, 6)}`;
      const def: BuildingDef = {
        id,
        type: this.selectedItemId,
        x: col,
        y: row,
      };
      const cmd = new PlaceBuildingCommand(this.config.buildings, def);
      this.commandHistory?.execute(cmd);
      this.rebuildBuildingInstances();
      this.renderBuildings();
      this.renderDecorations();
    } else if (this.selectedCategory === "decoration") {
      const def: DecorationDef = {
        type: this.selectedItemId as DecorationType,
        x: col,
        y: row,
      };
      const cmd = new PlaceDecorationCommand(this.config.decorations, def);
      this.commandHistory?.execute(cmd);
      this.renderDecorations();
    }
  }

  private eraseAt(col: number, row: number): void {
    const cmd = new EraseCommand(
      this.config.buildings,
      this.config.decorations,
      col,
      row,
    );
    if (!cmd.hasTarget) return;
    this.commandHistory?.execute(cmd);
    this.rebuildBuildingInstances();
    this.renderBuildings();
    this.renderDecorations();
  }

  // -----------------------------------------------------------------------
  // Rendering
  // -----------------------------------------------------------------------

  private renderTerrain(): void {
    const g = this.terrainLayer;
    g.clear();

    for (let row = 0; row < MAP_ROWS; row++) {
      for (let col = 0; col < MAP_COLS; col++) {
        const terrainId = this.config.terrain[row]?.[col] ?? TerrainType.grass;
        const baseColor = TERRAIN_COLORS[terrainId as TerrainType] ?? TERRAIN_COLORS[TerrainType.grass];
        const x = col * SCALED_TILE;
        const y = row * SCALED_TILE;

        g.rect(x, y, SCALED_TILE, SCALED_TILE);
        g.fill(baseColor);

        // Add subtle variation/pattern per terrain type.
        this.renderTerrainDetail(g, terrainId, x, y, col, row);
      }
    }
  }

  private renderTerrainDetail(
    g: Graphics,
    terrainId: number,
    x: number,
    y: number,
    col: number,
    row: number,
  ): void {
    const PX = SCALED_TILE / 16;
    // Pseudo-random based on position for consistent variation.
    const hash = ((col * 7 + row * 13) * 2654435761) >>> 0;
    const variation = (hash % 100) / 100;

    switch (terrainId) {
      case TerrainType.grass: {
        // Darker grass tufts.
        if (variation > 0.6) {
          g.circle(x + PX * 4, y + PX * 6, PX * 1.5);
          g.fill({ color: 0x3bba6a, alpha: 0.5 });
        }
        if (variation > 0.3 && variation < 0.5) {
          g.circle(x + PX * 11, y + PX * 10, PX * 1.2);
          g.fill({ color: 0x2ea55e, alpha: 0.4 });
        }
        break;
      }
      case TerrainType.dirt: {
        // Speckles.
        if (variation > 0.5) {
          g.circle(x + PX * 5, y + PX * 5, PX);
          g.fill({ color: 0x9e5518, alpha: 0.4 });
        }
        if (variation > 0.7) {
          g.circle(x + PX * 12, y + PX * 11, PX * 0.8);
          g.fill({ color: 0xa06020, alpha: 0.3 });
        }
        break;
      }
      case TerrainType.stone: {
        // Crack lines.
        if (variation > 0.4) {
          g.moveTo(x + PX * 3, y + PX * 4);
          g.lineTo(x + PX * 10, y + PX * 8);
          g.stroke({ width: 1, color: 0x666666, alpha: 0.4 });
        }
        if (variation > 0.6) {
          g.moveTo(x + PX * 8, y + PX * 2);
          g.lineTo(x + PX * 13, y + PX * 12);
          g.stroke({ width: 1, color: 0x777777, alpha: 0.3 });
        }
        break;
      }
      case TerrainType.water: {
        // Wave highlights.
        g.moveTo(x + PX * 3, y + PX * 6);
        g.quadraticCurveTo(x + PX * 8, y + PX * 4, x + PX * 13, y + PX * 6);
        g.stroke({ width: 1, color: 0x6eadfa, alpha: 0.5 });
        if (variation > 0.5) {
          g.moveTo(x + PX * 5, y + PX * 11);
          g.quadraticCurveTo(x + PX * 10, y + PX * 9, x + PX * 14, y + PX * 11);
          g.stroke({ width: 1, color: 0x6eadfa, alpha: 0.4 });
        }
        break;
      }
      case TerrainType.sand: {
        // Tiny dots.
        if (variation > 0.4) {
          g.circle(x + PX * 6, y + PX * 4, PX * 0.6);
          g.fill({ color: 0xe8cfa0, alpha: 0.5 });
        }
        break;
      }
      case TerrainType.path: {
        // Cobblestone pattern.
        const offX = (row % 2) * PX * 4;
        for (let r = 0; r < 2; r++) {
          for (let c = 0; c < 2; c++) {
            const cx = x + offX + c * PX * 8 + PX * 2;
            const cy = y + r * PX * 8 + PX * 2;
            g.roundRect(cx, cy, PX * 6, PX * 6, PX);
            g.fill({ color: 0xbfa07a, alpha: 0.6 });
            g.roundRect(cx, cy, PX * 6, PX * 6, PX);
            g.stroke({ width: 1, color: 0xa08060, alpha: 0.4 });
          }
        }
        break;
      }
    }
  }

  private renderBuildings(): void {
    this.buildingLayer.removeChildren();
    this.buildingInstances.clear();

    for (const def of this.config.buildings) {
      const type = def.type as BuildingType;
      const validTypes: BuildingType[] = ["cottage", "library", "shop", "plaza"];
      if (!validTypes.includes(type)) continue;

      const variant = def.variant ? parseInt(def.variant, 10) : 0;
      const building = new Building(def.id, type, def.x, def.y, def.owner, variant);
      this.buildingInstances.set(def, building);
      this.buildingLayer.addChild(building.container);
    }
  }

  private renderDecorations(): void {
    const g = this.decorationLayer;
    g.clear();

    for (const dec of this.config.decorations) {
      const x = dec.x * SCALED_TILE;
      const y = dec.y * SCALED_TILE;
      const PX = SCALED_TILE / 16;
      const cx = x + SCALED_TILE / 2;
      const cy = y + SCALED_TILE / 2;

      switch (dec.type) {
        case "tree_oak": {
          // Trunk.
          g.rect(cx - PX * 2, cy + PX * 2, PX * 4, PX * 6);
          g.fill(0x8b4513);
          // Canopy.
          g.circle(cx, cy - PX * 2, PX * 7);
          g.fill(0x228b22);
          g.circle(cx - PX * 3, cy, PX * 5);
          g.fill(0x2d9e2d);
          g.circle(cx + PX * 3, cy, PX * 5);
          g.fill(0x1e7a1e);
          break;
        }
        case "tree_pine": {
          // Trunk.
          g.rect(cx - PX * 1.5, cy + PX * 3, PX * 3, PX * 5);
          g.fill(0x8b4513);
          // Triangular layers.
          g.moveTo(cx, cy - PX * 7);
          g.lineTo(cx - PX * 5, cy);
          g.lineTo(cx + PX * 5, cy);
          g.closePath();
          g.fill(0x006400);
          g.moveTo(cx, cy - PX * 4);
          g.lineTo(cx - PX * 6, cy + PX * 3);
          g.lineTo(cx + PX * 6, cy + PX * 3);
          g.closePath();
          g.fill(0x007800);
          break;
        }
        case "bush": {
          g.circle(cx, cy + PX, PX * 5);
          g.fill(0x32cd32);
          g.circle(cx - PX * 3, cy + PX * 2, PX * 3.5);
          g.fill(0x28a428);
          g.circle(cx + PX * 3, cy + PX * 2, PX * 3.5);
          g.fill(0x28a428);
          break;
        }
        case "flower": {
          // Stem.
          g.moveTo(cx, cy + PX * 4);
          g.lineTo(cx, cy - PX * 2);
          g.stroke({ width: 2, color: 0x228b22 });
          // Petals.
          const petalColor = DECORATION_COLORS.flower;
          for (let i = 0; i < 5; i++) {
            const angle = (i / 5) * Math.PI * 2;
            g.circle(
              cx + Math.cos(angle) * PX * 2.5,
              cy - PX * 2 + Math.sin(angle) * PX * 2.5,
              PX * 1.8,
            );
            g.fill(petalColor);
          }
          // Center.
          g.circle(cx, cy - PX * 2, PX * 1.5);
          g.fill(0xffd700);
          break;
        }
        case "rock": {
          g.ellipse(cx, cy + PX * 2, PX * 6, PX * 4);
          g.fill(0x808080);
          g.ellipse(cx, cy + PX * 2, PX * 6, PX * 4);
          g.stroke({ width: 1, color: 0x606060 });
          // Highlight.
          g.ellipse(cx - PX * 2, cy, PX * 3, PX * 2);
          g.fill({ color: 0x999999, alpha: 0.5 });
          break;
        }
        case "fence_h": {
          // Horizontal fence segment.
          g.rect(x + PX, cy - PX, SCALED_TILE - PX * 2, PX * 3);
          g.fill(0xdeb887);
          g.stroke({ width: 1, color: 0xb8956a });
          // Posts.
          g.rect(x + PX * 2, cy - PX * 3, PX * 2, PX * 8);
          g.fill(0xdeb887);
          g.rect(x + SCALED_TILE - PX * 4, cy - PX * 3, PX * 2, PX * 8);
          g.fill(0xdeb887);
          break;
        }
        case "fence_v": {
          // Vertical fence segment.
          g.rect(cx - PX, y + PX, PX * 3, SCALED_TILE - PX * 2);
          g.fill(0xdeb887);
          g.stroke({ width: 1, color: 0xb8956a });
          // Posts.
          g.rect(cx - PX * 2, y + PX * 2, PX * 5, PX * 2);
          g.fill(0xdeb887);
          g.rect(cx - PX * 2, y + SCALED_TILE - PX * 4, PX * 5, PX * 2);
          g.fill(0xdeb887);
          break;
        }
        case "mushroom": {
          // Stem.
          g.rect(cx - PX * 1.5, cy + PX, PX * 3, PX * 5);
          g.fill(0xfffacd);
          // Cap.
          g.ellipse(cx, cy, PX * 4, PX * 3);
          g.fill(0xff6347);
          // Spots.
          g.circle(cx - PX * 1.5, cy - PX, PX);
          g.fill(0xffffff);
          g.circle(cx + PX * 1.5, cy - PX * 0.5, PX * 0.8);
          g.fill(0xffffff);
          break;
        }
        case "bench": {
          // Seat.
          g.rect(x + PX * 2, cy, SCALED_TILE - PX * 4, PX * 3);
          g.fill(0x8b4513);
          g.stroke({ width: 1, color: 0x654321 });
          // Back.
          g.rect(x + PX * 2, cy - PX * 3, SCALED_TILE - PX * 4, PX * 2);
          g.fill(0x8b4513);
          // Legs.
          g.rect(x + PX * 3, cy + PX * 3, PX * 2, PX * 3);
          g.fill(0x654321);
          g.rect(x + SCALED_TILE - PX * 5, cy + PX * 3, PX * 2, PX * 3);
          g.fill(0x654321);
          break;
        }
      }
    }
  }

  // -----------------------------------------------------------------------
  // Helpers
  // -----------------------------------------------------------------------

  private rebuildBuildingInstances(): void {
    // Called when buildings array changes externally (erase/undo).
    // renderBuildings() will recreate them.
  }

  private terrainNameToId(name: string): number {
    const map: Record<string, number> = {
      grass: TerrainType.grass,
      dirt: TerrainType.dirt,
      stone: TerrainType.stone,
      water: TerrainType.water,
      sand: TerrainType.sand,
      path: TerrainType.path,
    };
    return map[name] ?? TerrainType.grass;
  }
}
