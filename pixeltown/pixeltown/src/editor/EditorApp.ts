/**
 * Main editor orchestrator.
 * Manages the PixiJS application, editor modes (tabs), command history,
 * and save/load of the editor configuration JSON.
 */

import { Application } from "pixi.js";
import { MAP_COLS, MAP_ROWS, SCALED_TILE } from "@/config";
import { CommandHistory } from "./CommandHistory";
import { EditorGrid } from "./EditorGrid";
import { CharacterEditor } from "./modes/CharacterEditor";
import { TownMapEditor } from "./modes/TownMapEditor";
import { InteriorEditor } from "./modes/InteriorEditor";
import { FurniturePalette } from "./ui/FurniturePalette";
import { TerrainType } from "./types";
import type { EditorConfig, TownMapConfig, InteriorConfig, CharacterConfig } from "./types";

export type EditorMode = "town" | "interior" | "character";

export class EditorApp {
  readonly app: Application;
  readonly history: CommandHistory;
  readonly grid: EditorGrid;
  readonly townMapEditor: TownMapEditor;
  readonly interiorEditor: InteriorEditor;
  readonly furniturePalette: FurniturePalette;
  readonly characterEditor: CharacterEditor;

  private _mode: EditorMode = "town";
  private config: EditorConfig;

  constructor(app: Application) {
    this.app = app;
    this.history = new CommandHistory();
    this.grid = new EditorGrid();
    this.config = EditorApp.defaultConfig();

    // Create TownMapEditor with the config's townMap.
    this.townMapEditor = new TownMapEditor(this.config.townMap);

    // Create InteriorEditor and FurniturePalette.
    this.interiorEditor = new InteriorEditor();
    this.furniturePalette = new FurniturePalette();

    // Create CharacterEditor.
    this.characterEditor = new CharacterEditor();
    this.furniturePalette.onSelect = (type: string) => {
      this.interiorEditor.setPlacementType(type);
    };

    // Add grid overlay to the stage.
    this.app.stage.addChild(this.grid.container);

    // Attach town map editor by default (town mode is initial).
    this.townMapEditor.attach(this.app.stage, this.history, this.grid);

    // Re-render on undo/redo so visual state stays in sync.
    const prevOnChange = this.history.onChange;
    this.history.onChange = () => {
      prevOnChange?.();
      if (this._mode === "town") {
        this.townMapEditor.render();
      } else if (this._mode === "interior") {
        this.interiorEditor.redraw();
      } else if (this._mode === "character") {
        // Character editor UI is refreshed internally by commands.
      }
    };
  }

  // -----------------------------------------------------------------------
  // Mode / tab switching
  // -----------------------------------------------------------------------

  get mode(): EditorMode {
    return this._mode;
  }

  setMode(mode: EditorMode): void {
    if (mode === this._mode) return;

    // Detach current mode.
    if (this._mode === "town") {
      this.townMapEditor.detach();
    } else if (this._mode === "interior") {
      this.interiorEditor.detach();
      this.furniturePalette.detach();
    } else if (this._mode === "character") {
      this.characterEditor.detach();
    }

    this._mode = mode;

    // Attach new mode.
    if (mode === "town") {
      this.townMapEditor.attach(this.app.stage, this.history, this.grid);
    } else if (mode === "interior") {
      // Hide the grid in interior mode (not tile-based).
      this.grid.container.visible = false;
      // Populate room IDs from buildings in the town config.
      const buildingIds = this.config.townMap.buildings.map((b) => b.id);
      if (buildingIds.length === 0) buildingIds.push("default");
      this.interiorEditor.setRoomIds(buildingIds);
      this.interiorEditor.attach(this.app.stage, this.history);
      // Attach furniture palette to sidebar.
      const sidebar = document.getElementById("sidebar");
      if (sidebar) this.furniturePalette.attach(sidebar);
    } else if (mode === "character") {
      this.grid.container.visible = false;
      const sidebar = document.getElementById("sidebar");
      const properties = document.getElementById("properties");
      const canvasContainer = document.getElementById("canvas-container");
      if (sidebar && properties && canvasContainer) {
        void this.characterEditor.attach(
          sidebar, properties, canvasContainer, this.history, this.app,
        );
      }
    }

    // Restore grid visibility when leaving interior/character mode.
    if (mode !== "interior" && mode !== "character") {
      this.grid.container.visible = this.grid.visible;
    }

    this.updateStatus(`Switched to ${mode} mode`);
  }

  // -----------------------------------------------------------------------
  // Save / Load
  // -----------------------------------------------------------------------

  /** Download current config as a JSON file. */
  save(): void {
    // Sync all editor states into config before saving.
    this.config.townMap = this.townMapEditor.getConfig();
    this.config.interior = this.interiorEditor.getConfig();
    this.config.characters = this.characterEditor.getConfig();

    const json = JSON.stringify(this.config, null, 2);
    const blob = new Blob([json], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "pixeltown-config.json";
    a.click();
    URL.revokeObjectURL(url);
    this.updateStatus("Saved pixeltown-config.json");
  }

  /** Load a JSON config from a File object. */
  async load(file: File): Promise<void> {
    try {
      const text = await file.text();
      const parsed = JSON.parse(text) as Partial<EditorConfig>;
      if (parsed.townMap) {
        this.config.townMap = parsed.townMap;
        this.townMapEditor.loadConfig(parsed.townMap);
      }
      if (parsed.interior) {
        this.config.interior = parsed.interior;
        this.interiorEditor.loadConfig(parsed.interior);
      }
      if (parsed.characters) {
        this.config.characters = parsed.characters;
        this.characterEditor.loadConfig(parsed.characters);
      }
      this.updateStatus(`Loaded ${file.name}`);
    } catch (err) {
      console.error("Failed to load config:", err);
      this.updateStatus("Error loading file");
    }
  }

  /** Get a reference to the current config (for commands / modes). */
  getConfig(): EditorConfig {
    this.config.townMap = this.townMapEditor.getConfig();
    this.config.interior = this.interiorEditor.getConfig();
    this.config.characters = this.characterEditor.getConfig();
    return this.config;
  }

  // -----------------------------------------------------------------------
  // Helpers
  // -----------------------------------------------------------------------

  private updateStatus(text: string): void {
    const el = document.getElementById("status-text");
    if (el) el.textContent = text;
  }

  /** Create a blank default config. */
  static defaultConfig(): EditorConfig {
    const terrain: number[][] = [];
    for (let r = 0; r < MAP_ROWS; r++) {
      terrain.push(new Array<number>(MAP_COLS).fill(TerrainType.grass));
    }

    const townMap: TownMapConfig = {
      terrain,
      buildings: [],
      decorations: [],
    };

    const interior: InteriorConfig = {
      layouts: {},
    };

    const characters: CharacterConfig = {
      agents: {},
      defaultSheet: "default",
    };

    return { townMap, interior, characters };
  }
}
